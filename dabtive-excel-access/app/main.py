from __future__ import annotations

import mimetypes
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import Base, SessionLocal, engine, get_db
from app.jobs import enqueue
from app.migrations import run_lightweight_migrations
from app.models import Campaign, CampaignImage, Download, Job, Lead, SiteSetting
from app.security import decrypt_text, encrypt_text, random_password, random_token
from app.services.leads_export import MIME_XLSX, build_leads_xlsx

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
LOCAL_TZ = ZoneInfo(settings.timezone)

app = FastAPI(title=settings.app_name, docs_url=None if settings.environment == "production" else "/docs")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=settings.environment == "production",
    max_age=60 * 60 * 12,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_expired(value: datetime | None) -> bool:
    value = aware(value)
    return value is None or value <= utcnow()


def local_datetime(value: datetime | None) -> str:
    value = aware(value)
    if not value:
        return "-"
    return value.astimezone(LOCAL_TZ).strftime("%d %b %Y, %H:%M WIB")


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower().strip())
    return value.strip("-")[:100] or f"file-{secrets.token_hex(3)}"


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = random_token(18)
        request.session["csrf"] = token
    return token


def require_csrf(request: Request, token: str) -> None:
    if not secrets.compare_digest(request.session.get("csrf", ""), token or ""):
        raise HTTPException(403, "CSRF token tidak valid")


def is_admin(request: Request) -> bool:
    return request.session.get("admin") is True


def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(401, "Login admin diperlukan")


def render(request: Request, template: str, context: dict | None = None, status_code: int = 200):
    payload = {
        "request": request,
        "settings": settings,
        "csrf": csrf_token(request),
        "is_admin": is_admin(request),
        "local_datetime": local_datetime,
    }
    if context:
        payload.update(context)
    return templates.TemplateResponse(template, payload, status_code=status_code)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    return digits[:20]


def save_upload(upload: UploadFile, slug: str) -> str:
    filename = upload.filename or "master.xlsx"
    if Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(400, "File master harus berformat .xlsx")
    destination = settings.data_path / "uploads" / f"{slug}-master.xlsx"
    temporary = destination.with_suffix(".tmp")
    size = 0
    with temporary.open("wb") as target:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                temporary.unlink(missing_ok=True)
                raise HTTPException(413, f"Ukuran file maksimal {settings.max_upload_mb} MB")
            target.write(chunk)
    if size < 4 or temporary.read_bytes()[:2] != b"PK":
        temporary.unlink(missing_ok=True)
        raise HTTPException(400, "File bukan .xlsx yang valid")
    temporary.replace(destination)
    return str(destination)


def save_cover(upload: UploadFile, slug: str, old_path: str | None = None) -> str:
    filename = upload.filename or "cover.jpg"
    extension = Path(filename).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "Gambar harus JPG, PNG, atau WEBP")
    destination = settings.data_path / "images" / f"{slug}-cover{extension}"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    size = 0
    with temporary.open("wb") as target:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > 10 * 1024 * 1024:
                temporary.unlink(missing_ok=True)
                raise HTTPException(413, "Ukuran screenshot maksimal 10 MB")
            target.write(chunk)
    header = temporary.read_bytes()[:16]
    valid = (
        (extension == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
        or (extension == ".webp" and header[:4] == b"RIFF" and header[8:12] == b"WEBP")
    )
    if not valid:
        temporary.unlink(missing_ok=True)
        raise HTTPException(400, "Isi file gambar tidak valid")
    temporary.replace(destination)
    if old_path and old_path != str(destination):
        Path(old_path).unlink(missing_ok=True)
    return str(destination)


def save_gallery_image(upload: UploadFile, campaign: Campaign, sort_order: int) -> CampaignImage:
    filename = upload.filename or "preview.jpg"
    extension = Path(filename).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "Screenshot harus JPG, PNG, atau WEBP")
    unique_name = f"{campaign.slug}-{sort_order:02d}-{secrets.token_hex(5)}{extension}"
    destination = settings.data_path / "images" / unique_name
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    size = 0
    with temporary.open("wb") as target:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > 10 * 1024 * 1024:
                temporary.unlink(missing_ok=True)
                raise HTTPException(413, "Ukuran setiap screenshot maksimal 10 MB")
            target.write(chunk)
    header = temporary.read_bytes()[:16]
    valid = (
        (extension == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
        or (extension == ".webp" and header[:4] == b"RIFF" and header[8:12] == b"WEBP")
    )
    if not valid:
        temporary.unlink(missing_ok=True)
        raise HTTPException(400, "Isi file screenshot tidak valid")
    temporary.replace(destination)
    return CampaignImage(
        campaign_id=campaign.id,
        file_path=str(destination),
        alt_text=f"Preview {campaign.name}",
        sort_order=sort_order,
    )


def import_legacy_cover_images(db: Session) -> None:
    campaigns = db.execute(select(Campaign).options(selectinload(Campaign.images))).scalars().all()
    changed = False
    for campaign in campaigns:
        if campaign.cover_image and Path(campaign.cover_image).exists() and not campaign.images:
            db.add(CampaignImage(
                campaign_id=campaign.id,
                file_path=campaign.cover_image,
                alt_text=f"Preview {campaign.name}",
                sort_order=0,
            ))
            campaign.cover_image = None
            changed = True
    if changed:
        db.commit()


def get_campaign_or_404(db: Session, slug: str, *, public: bool = False) -> Campaign:
    query = select(Campaign).where(Campaign.slug == slug).options(selectinload(Campaign.images))
    if public:
        query = query.where(Campaign.active.is_(True))
    campaign = db.execute(query).scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign tidak ditemukan")
    return campaign


def get_lead_or_404(db: Session, token: str) -> Lead:
    lead = db.execute(select(Lead).where(Lead.access_token == token)).scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Halaman akses tidak ditemukan")
    return lead


def site_setting(db: Session) -> SiteSetting:
    row = db.get(SiteSetting, 1)
    if row:
        return row
    first = db.execute(select(Campaign).where(Campaign.active.is_(True)).order_by(Campaign.id)).scalars().first()
    row = SiteSetting(id=1, home_mode="redirect", home_campaign_id=first.id if first else None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_download_for_lead(db: Session, lead: Lead) -> Download:
    if lead.download:
        return lead.download
    download = Download(
        token=random_token(32),
        lead_id=lead.id,
        expires_at=utcnow() + timedelta(hours=lead.campaign.expiry_hours),
        max_downloads=lead.campaign.max_downloads,
    )
    db.add(download)
    db.commit()
    db.refresh(download)
    return download


@app.on_event("startup")
def startup() -> None:
    settings.data_path
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    with SessionLocal() as db:
        if not db.scalar(select(func.count(Campaign.id))):
            source = BASE_DIR.parent / "seed" / "dabtive-campaign-index-demo.xlsx"
            destination = settings.data_path / "uploads" / "campaign-index-master.xlsx"
            if source.exists() and not destination.exists():
                shutil.copy2(source, destination)
            seed_campaign = Campaign(
                name="Independence Campaign Index",
                slug="campaign-index",
                active=True,
                landing_title="Independence Campaign Index",
                landing_description="Data dan analisis untuk campaign yang lebih merdeka dan terukur.",
                landing_body=(
                    "Independence Campaign Index adalah template Excel gratis untuk membantu Anda "
                    "mengevaluasi performa campaign di berbagai channel secara cepat, akurat, dan independen."
                ),
                highlights=(
                    "100+ metrik campaign siap pakai\n"
                    "Dashboard ringkas dan mudah dipahami\n"
                    "Benchmark industri dan tren terbaru\n"
                    "Mendukung keputusan berbasis data\n"
                    "Format Excel siap digunakan"
                ),
                business_types=(
                    "FMCG\nRetail\nEducation / Campus\nGovernment\nProperty\nTechnology\n"
                    "Beauty & Personal Care\nFood & Beverage\nHospitality & Tourism\n"
                    "Professional Services\nUMKM\nOther"
                ),
                master_file=str(destination) if destination.exists() else None,
                expiry_hours=48,
                max_downloads=2,
                product_mode="free",
            )
            db.add(seed_campaign)
            db.flush()
            for order, filename in enumerate(("campaign-preview-1.png", "campaign-preview-2.png")):
                image_source = BASE_DIR.parent / "seed" / filename
                image_destination = settings.data_path / "images" / filename
                if image_source.exists() and not image_destination.exists():
                    shutil.copy2(image_source, image_destination)
                if image_destination.exists():
                    db.add(CampaignImage(
                        campaign_id=seed_campaign.id,
                        file_path=str(image_destination),
                        alt_text=f"Preview {seed_campaign.name} {order + 1}",
                        sort_order=order,
                    ))
            db.commit()
        site_setting(db)
        import_legacy_cover_images(db)


@app.get("/health", response_class=JSONResponse)
def health(db: Session = Depends(get_db)):
    db.execute(select(func.count(Campaign.id))).scalar_one()
    return {"ok": True, "app": settings.app_name, "time": utcnow().isoformat()}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    homepage = site_setting(db)
    if homepage.home_mode == "redirect" and homepage.home_campaign_id:
        campaign = db.get(Campaign, homepage.home_campaign_id)
        if campaign and campaign.active:
            return RedirectResponse(f"/c/{campaign.slug}", status_code=301)
    campaigns = db.execute(
        select(Campaign)
        .where(Campaign.active.is_(True))
        .options(selectinload(Campaign.images))
        .order_by(Campaign.created_at.desc())
    ).scalars().all()
    return render(request, "public/home.html", {"campaigns": campaigns})


@app.get("/media/campaigns/{campaign_id}/cover")
def campaign_cover(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign or not campaign.cover_image or not Path(campaign.cover_image).exists():
        raise HTTPException(404, "Gambar tidak ditemukan")
    media_type = mimetypes.guess_type(campaign.cover_image)[0] or "application/octet-stream"
    return FileResponse(campaign.cover_image, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/media/campaigns/{campaign_id}/images/{image_id}")
def campaign_image(campaign_id: int, image_id: int, db: Session = Depends(get_db)):
    image = db.execute(
        select(CampaignImage).where(
            CampaignImage.id == image_id,
            CampaignImage.campaign_id == campaign_id,
        )
    ).scalar_one_or_none()
    if not image or not Path(image.file_path).exists():
        raise HTTPException(404, "Gambar tidak ditemukan")
    media_type = mimetypes.guess_type(image.file_path)[0] or "application/octet-stream"
    return FileResponse(image.file_path, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"})


# ------------------------- Public request flow -------------------------
@app.get("/c/{slug}", response_class=HTMLResponse)
def campaign_page(slug: str, request: Request, db: Session = Depends(get_db)):
    campaign = db.execute(
        select(Campaign)
        .where(Campaign.slug == slug, Campaign.active.is_(True))
        .options(selectinload(Campaign.images))
    ).scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign tidak ditemukan")
    return render(request, "public/request.html", {"campaign": campaign})


@app.post("/c/{slug}")
def campaign_submit(
    slug: str,
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    business_type: str = Form(...),
    whatsapp: str = Form(...),
    website: str = Form(""),
    consent: str | None = Form(None),
    csrf_form: str = Form(..., alias="_csrf"),
    db: Session = Depends(get_db),
):
    require_csrf(request, csrf_form)
    campaign = get_campaign_or_404(db, slug, public=True)
    values = {"name": name, "email": email, "business_type": business_type, "whatsapp": whatsapp}
    if website:
        return RedirectResponse(f"/c/{slug}?submitted=1", 303)
    if consent != "on":
        return render(request, "public/request.html", {"campaign": campaign, "error": "Persetujuan diperlukan untuk membuat akses.", "values": values}, 400)
    clean_name = name.strip()[:180]
    clean_email = email.strip().lower()[:254]
    clean_business = business_type.strip()[:180]
    clean_whatsapp = normalize_phone(whatsapp)
    if not clean_name or "@" not in clean_email or "." not in clean_email.rsplit("@", 1)[-1]:
        return render(request, "public/request.html", {"campaign": campaign, "error": "Nama dan email aktif wajib diisi dengan benar.", "values": values}, 400)
    if clean_business not in campaign.business_type_options:
        return render(request, "public/request.html", {"campaign": campaign, "error": "Jenis bisnis tidak valid.", "values": values}, 400)
    if len(clean_whatsapp) < 9:
        return render(request, "public/request.html", {"campaign": campaign, "error": "Nomor WhatsApp belum valid.", "values": values}, 400)
    if not campaign.master_file or not Path(campaign.master_file).exists():
        return render(request, "public/request.html", {"campaign": campaign, "error": "File belum tersedia. Silakan hubungi admin Dabtive.", "values": values}, 503)

    since = utcnow() - timedelta(hours=1)
    ip = client_ip(request)
    email_count = db.scalar(select(func.count(Lead.id)).where(Lead.email == clean_email, Lead.created_at >= since)) or 0
    ip_count = db.scalar(select(func.count(Lead.id)).where(Lead.request_ip == ip, Lead.created_at >= since)) or 0
    if email_count >= settings.rate_limit_email_per_hour or ip_count >= settings.rate_limit_ip_per_hour:
        return render(request, "public/request.html", {"campaign": campaign, "error": "Terlalu banyak permintaan. Coba lagi setelah satu jam.", "values": values}, 429)

    paid = campaign.is_paid
    password = random_password()
    lead = Lead(
        campaign_id=campaign.id,
        name=clean_name,
        email=clean_email,
        business_type=clean_business,
        whatsapp=clean_whatsapp,
        request_ip=ip,
        user_agent=request.headers.get("user-agent", "")[:300] or None,
        status="awaiting_payment" if paid else "queued",
        payment_status="pending" if paid else "not_required",
        payment_amount=campaign.price_amount if paid else 0,
        license_id=f"TMP-{random_token(6)}",
        access_token=random_token(32),
        access_password_enc=encrypt_text(password),
    )
    db.add(lead)
    db.flush()
    lead.license_id = f"DAB-{utcnow():%y%m%d}-{lead.id:06d}"
    db.commit()

    if not paid:
        create_download_for_lead(db, lead)
        enqueue(db, "prepare_download", {"lead_id": lead.id})
    return RedirectResponse(f"/r/{lead.access_token}", 303)


@app.get("/r/{token}", response_class=HTMLResponse)
def access_page(token: str, request: Request, db: Session = Depends(get_db)):
    lead = get_lead_or_404(db, token)
    password = decrypt_text(lead.access_password_enc) if lead.status == "ready" else ""
    return render(request, "public/access.html", {
        "lead": lead,
        "campaign": lead.campaign,
        "download": lead.download,
        "password": password,
        "expired": is_expired(lead.download.expires_at) if lead.download else False,
    })


@app.get("/d/{token}")
def download_file(token: str, db: Session = Depends(get_db)):
    download = db.execute(select(Download).where(Download.token == token)).scalar_one_or_none()
    if not download:
        raise HTTPException(404, "Link download tidak ditemukan")
    if is_expired(download.expires_at):
        raise HTTPException(410, "Link download sudah kedaluwarsa")
    if download.download_count >= download.max_downloads:
        raise HTTPException(410, "Batas download sudah tercapai")
    if download.lead.status != "ready" or not download.file_path or not Path(download.file_path).exists():
        raise HTTPException(409, "File masih diproses")
    download.download_count += 1
    db.commit()
    return FileResponse(
        download.file_path,
        filename=Path(download.file_path).name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Cache-Control": "private, no-store"},
    )


# ------------------------- Admin -------------------------
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if is_admin(request):
        return RedirectResponse("/admin", 303)
    return render(request, "admin/login.html")


@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...), csrf_form: str = Form(..., alias="_csrf")):
    require_csrf(request, csrf_form)
    if not secrets.compare_digest(password, settings.admin_password):
        return render(request, "admin/login.html", {"error": "Password admin salah."}, 400)
    request.session["admin"] = True
    return RedirectResponse("/admin", 303)


@app.post("/admin/logout")
def admin_logout(request: Request, csrf_form: str = Form(..., alias="_csrf")):
    require_csrf(request, csrf_form)
    request.session.clear()
    return RedirectResponse("/admin/login", 303)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    stats = {
        "campaigns": db.scalar(select(func.count(Campaign.id))) or 0,
        "leads": db.scalar(select(func.count(Lead.id))) or 0,
        "ready": db.scalar(select(func.count(Lead.id)).where(Lead.status == "ready")) or 0,
        "downloads": db.scalar(select(func.coalesce(func.sum(Download.download_count), 0))) or 0,
        "pending_payment": db.scalar(select(func.count(Lead.id)).where(Lead.payment_status == "pending")) or 0,
    }
    campaigns = db.execute(select(Campaign).order_by(Campaign.created_at.desc())).scalars().all()
    leads = db.execute(
        select(Lead)
        .options(selectinload(Lead.campaign), selectinload(Lead.download))
        .order_by(Lead.created_at.desc())
    ).scalars().all()
    failed_jobs = db.execute(select(Job).where(Job.status == "failed").order_by(Job.id.desc()).limit(5)).scalars().all()
    return render(request, "admin/dashboard.html", {
        "stats": stats,
        "campaigns": campaigns,
        "leads": leads,
        "failed_jobs": failed_jobs,
        "smtp_ready": settings.smtp_enabled,
        "home_setting": site_setting(db),
    })


@app.get("/admin/settings", response_class=HTMLResponse)
def admin_settings_page(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    campaigns = db.execute(select(Campaign).order_by(Campaign.name)).scalars().all()
    return render(request, "admin/settings.html", {"home_setting": site_setting(db), "campaigns": campaigns})


@app.post("/admin/settings")
def admin_settings_update(
    request: Request,
    home_mode: str = Form("redirect"),
    home_campaign_id: int | None = Form(None),
    csrf_form: str = Form(..., alias="_csrf"),
    db: Session = Depends(get_db),
):
    require_admin(request)
    require_csrf(request, csrf_form)
    row = site_setting(db)
    row.home_mode = home_mode if home_mode in {"redirect", "catalog"} else "redirect"
    row.home_campaign_id = home_campaign_id or None
    if row.home_mode == "redirect" and row.home_campaign_id:
        campaign = db.get(Campaign, row.home_campaign_id)
        if not campaign:
            raise HTTPException(400, "Campaign homepage tidak ditemukan")
    db.commit()
    return RedirectResponse("/admin/settings?saved=1", 303)


@app.get("/admin/campaigns/new", response_class=HTMLResponse)
def campaign_new_page(request: Request):
    require_admin(request)
    return render(request, "admin/campaign_form.html", {"campaign": None})


@app.post("/admin/campaigns/new")
def campaign_new(
    request: Request,
    name: str = Form(...),
    slug: str = Form(""),
    landing_title: str = Form(...),
    landing_description: str = Form(...),
    landing_body: str = Form(""),
    highlights: str = Form(""),
    business_types: str = Form(...),
    expiry_hours: int = Form(48),
    max_downloads: int = Form(2),
    active: str | None = Form(None),
    paid_product: str | None = Form(None),
    price_amount: int = Form(0),
    checkout_url: str = Form(""),
    payment_instructions: str = Form(""),
    purchase_button_label: str = Form("BELI SEKARANG"),
    master_file: UploadFile | None = File(None),
    gallery_images: list[UploadFile] = File(default=[]),
    csrf_form: str = Form(..., alias="_csrf"),
    db: Session = Depends(get_db),
):
    require_admin(request)
    require_csrf(request, csrf_form)
    final_slug = slugify(slug or name)
    campaign = Campaign(
        name=name.strip()[:180],
        slug=final_slug,
        active=active == "on",
        landing_title=landing_title.strip()[:220],
        landing_description=landing_description.strip(),
        landing_body=landing_body.strip(),
        highlights=highlights.strip(),
        business_types=business_types.strip(),
        expiry_hours=max(1, min(expiry_hours, 720)),
        max_downloads=max(1, min(max_downloads, 20)),
        product_mode="paid" if paid_product == "on" else "free",
        price_amount=max(0, price_amount),
        checkout_url=checkout_url.strip()[:700] or None,
        payment_instructions=payment_instructions.strip(),
        purchase_button_label=purchase_button_label.strip()[:80] or "BELI SEKARANG",
    )
    db.add(campaign)
    try:
        db.flush()
        if master_file and master_file.filename:
            campaign.master_file = save_upload(master_file, final_slug)
        valid_images = [image for image in gallery_images if image and image.filename]
        if len(valid_images) > 8:
            raise HTTPException(400, "Maksimal 8 screenshot per produk")
        for index, image in enumerate(valid_images):
            db.add(save_gallery_image(image, campaign, index))
        db.commit()
    except IntegrityError:
        db.rollback()
        return render(request, "admin/campaign_form.html", {"campaign": campaign, "error": "Slug sudah digunakan."}, 400)
    return RedirectResponse(f"/admin/campaigns/{campaign.id}", 303)


@app.get("/admin/campaigns/{campaign_id}", response_class=HTMLResponse)
def campaign_detail(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    campaign = db.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(selectinload(Campaign.images))
    ).scalar_one_or_none()
    if not campaign:
        raise HTTPException(404)
    leads = db.execute(
        select(Lead)
        .where(Lead.campaign_id == campaign.id)
        .options(selectinload(Lead.download))
        .order_by(Lead.created_at.desc())
    ).scalars().all()
    return render(request, "admin/campaign_detail.html", {"campaign": campaign, "leads": leads})


@app.post("/admin/campaigns/{campaign_id}")
def campaign_update(
    campaign_id: int,
    request: Request,
    name: str = Form(...),
    landing_title: str = Form(...),
    landing_description: str = Form(...),
    landing_body: str = Form(""),
    highlights: str = Form(""),
    business_types: str = Form(...),
    expiry_hours: int = Form(48),
    max_downloads: int = Form(2),
    active: str | None = Form(None),
    paid_product: str | None = Form(None),
    price_amount: int = Form(0),
    checkout_url: str = Form(""),
    payment_instructions: str = Form(""),
    purchase_button_label: str = Form("BELI SEKARANG"),
    master_file: UploadFile | None = File(None),
    gallery_images: list[UploadFile] = File(default=[]),
    csrf_form: str = Form(..., alias="_csrf"),
    db: Session = Depends(get_db),
):
    require_admin(request)
    require_csrf(request, csrf_form)
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404)
    campaign.name = name.strip()[:180]
    campaign.landing_title = landing_title.strip()[:220]
    campaign.landing_description = landing_description.strip()
    campaign.landing_body = landing_body.strip()
    campaign.highlights = highlights.strip()
    campaign.business_types = business_types.strip()
    campaign.expiry_hours = max(1, min(expiry_hours, 720))
    campaign.max_downloads = max(1, min(max_downloads, 20))
    campaign.active = active == "on"
    campaign.product_mode = "paid" if paid_product == "on" else "free"
    campaign.price_amount = max(0, price_amount)
    campaign.checkout_url = checkout_url.strip()[:700] or None
    campaign.payment_instructions = payment_instructions.strip()
    campaign.purchase_button_label = purchase_button_label.strip()[:80] or "BELI SEKARANG"
    if master_file and master_file.filename:
        campaign.master_file = save_upload(master_file, campaign.slug)
    valid_images = [image for image in gallery_images if image and image.filename]
    if len(campaign.images) + len(valid_images) > 8:
        raise HTTPException(400, "Maksimal 8 screenshot per produk")
    next_order = max((image.sort_order for image in campaign.images), default=-1) + 1
    for offset, image in enumerate(valid_images):
        db.add(save_gallery_image(image, campaign, next_order + offset))
    db.commit()
    return RedirectResponse(f"/admin/campaigns/{campaign.id}?saved=1", 303)


@app.post("/admin/campaigns/{campaign_id}/images/{image_id}/delete")
def campaign_image_delete(
    campaign_id: int,
    image_id: int,
    request: Request,
    csrf_form: str = Form(..., alias="_csrf"),
    db: Session = Depends(get_db),
):
    require_admin(request)
    require_csrf(request, csrf_form)
    image = db.execute(
        select(CampaignImage).where(
            CampaignImage.id == image_id,
            CampaignImage.campaign_id == campaign_id,
        )
    ).scalar_one_or_none()
    if not image:
        raise HTTPException(404, "Screenshot tidak ditemukan")
    path = Path(image.file_path)
    db.delete(image)
    db.commit()
    path.unlink(missing_ok=True)
    return RedirectResponse(f"/admin/campaigns/{campaign_id}?saved=1", 303)


@app.post("/admin/leads/{lead_id}/mark-paid")
def mark_lead_paid(
    lead_id: int,
    request: Request,
    csrf_form: str = Form(..., alias="_csrf"),
    db: Session = Depends(get_db),
):
    require_admin(request)
    require_csrf(request, csrf_form)
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead tidak ditemukan")
    if not lead.campaign.is_paid:
        raise HTTPException(400, "Campaign ini bukan produk berbayar")
    if lead.payment_status != "paid":
        lead.payment_status = "paid"
        lead.paid_at = utcnow()
        lead.status = "queued"
        db.commit()
        create_download_for_lead(db, lead)
        enqueue(db, "prepare_download", {"lead_id": lead.id})
    destination = request.headers.get("referer") or "/admin"
    return RedirectResponse(destination, 303)


@app.get("/admin/leads.xlsx")
def export_leads(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    leads = db.execute(
        select(Lead)
        .options(selectinload(Lead.campaign), selectinload(Lead.download))
        .order_by(Lead.created_at.desc())
    ).scalars().all()
    rows = []
    for lead in leads:
        rows.append({
            "created_at": local_datetime(lead.created_at),
            "campaign": lead.campaign.name,
            "name": lead.name,
            "email": lead.email,
            "business_type": lead.business_type,
            "whatsapp": lead.whatsapp,
            "license_id": lead.license_id,
            "status": lead.status,
            "payment_status": lead.payment_status,
            "payment_amount": lead.payment_amount,
            "downloads": lead.download.download_count if lead.download else 0,
            "expires_at": local_datetime(lead.download.expires_at if lead.download else None),
        })
    data = build_leads_xlsx(rows, local_datetime(utcnow()))
    filename = f"dabtive-leads-{utcnow():%Y%m%d-%H%M}.xlsx"
    return Response(
        content=data,
        media_type=MIME_XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@app.get("/admin/leads.csv")
def legacy_export_leads(request: Request):
    require_admin(request)
    return RedirectResponse("/admin/leads.xlsx", 307)


@app.exception_handler(401)
def unauthorized(request: Request, exc: HTTPException):
    return RedirectResponse("/admin/login", 303)


@app.exception_handler(404)
def not_found(request: Request, exc: HTTPException):
    return render(request, "public/error.html", {"title": "Halaman tidak ditemukan", "message": str(exc.detail)}, 404)


@app.exception_handler(410)
def gone(request: Request, exc: HTTPException):
    return render(request, "public/error.html", {"title": "Akses sudah berakhir", "message": str(exc.detail)}, 410)
