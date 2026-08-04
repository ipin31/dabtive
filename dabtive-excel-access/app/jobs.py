from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models import Download, Job, Lead
from app.security import decrypt_text
from app.services.emailer import send_email
from app.services.files import encrypt_excel_file, safe_filename

settings = get_settings()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(db: Session, kind: str, payload: dict) -> Job:
    job = Job(kind=kind, payload=payload)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def process_job(db: Session, job: Job) -> None:
    if job.kind != "prepare_download":
        raise ValueError(f"Unknown job kind: {job.kind}")
    _prepare_download(db, job.payload)


def _prepare_download(db: Session, payload: dict) -> None:
    lead = db.get(Lead, payload["lead_id"])
    if not lead or not lead.download:
        raise ValueError("Lead atau download tidak ditemukan")
    campaign = lead.campaign
    if not campaign.master_file:
        raise ValueError("Master Excel belum di-upload oleh admin")
    master = Path(campaign.master_file)
    if not master.exists():
        raise FileNotFoundError("Master Excel tidak ditemukan di storage")
    password = decrypt_text(lead.access_password_enc)
    if not password:
        raise ValueError("Password lead tidak dapat dibaca; periksa SECRET_KEY")

    filename = f"{safe_filename(campaign.name)}-{lead.license_id}.xlsx"
    output = settings.data_path / "generated" / filename
    lead.status = "processing"
    lead.error_message = None
    db.commit()

    lead.download.file_path = encrypt_excel_file(master, output, password)
    lead.status = "ready"
    lead.ready_at = utcnow()
    db.commit()

    access_url = f"{settings.app_url.rstrip('/')}/r/{lead.access_token}"
    expires_text = lead.download.expires_at.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    text = (
        f"Halo {lead.name},\n\n"
        f"File {campaign.name} sudah siap.\n\n"
        f"Halaman akses: {access_url}\n"
        f"Password Excel: {password}\n"
        f"License ID: {lead.license_id}\n"
        f"Berlaku sampai: {expires_text}\n"
        f"Batas download: {lead.download.max_downloads} kali\n\n"
        "Simpan password tersebut. File Excel tidak dapat dibuka tanpa password."
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#111">
      <div style="border-top:8px solid #e1162b;padding:24px;border-left:1px solid #ddd;border-right:1px solid #ddd;border-bottom:1px solid #ddd">
        <p style="font-size:12px;letter-spacing:.12em;font-weight:700">DABTIVE SECURE ACCESS</p>
        <h1 style="font-size:28px">File kamu sudah siap.</h1>
        <p>Halo <b>{lead.name}</b>, akses personal untuk <b>{campaign.name}</b> telah dibuat.</p>
        <div style="background:#111;color:white;padding:18px;margin:22px 0">
          <small style="color:#aaa">PASSWORD EXCEL</small><br>
          <strong style="font-size:24px;letter-spacing:.04em">{password}</strong>
        </div>
        <p><b>License ID:</b> {lead.license_id}<br><b>Berlaku sampai:</b> {expires_text}<br><b>Batas download:</b> {lead.download.max_downloads} kali</p>
        <p><a href="{access_url}" style="display:inline-block;background:#e1162b;color:white;text-decoration:none;padding:14px 20px;font-weight:700">BUKA HALAMAN AKSES →</a></p>
      </div>
    </div>
    """
    try:
        send_email(lead.email, f"Akses {campaign.name}", text, html)
    except Exception as exc:
        # File remains available even if email delivery fails.
        print(f"Email delivery failed for lead {lead.id}: {exc}")
