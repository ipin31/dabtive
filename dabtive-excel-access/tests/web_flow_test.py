from __future__ import annotations
import os
import re
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def csrf(html: str) -> str:
    match = re.search(r'name="_csrf" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        os.environ["DATABASE_URL"] = f"sqlite:///{root / 'test.db'}"
        os.environ["DATA_DIR"] = str(root / "data")
        os.environ["SECRET_KEY"] = "test-secret-key-abcdefghijklmnopqrstuvwxyz"
        os.environ["ADMIN_PASSWORD"] = "admin-test"
        os.environ["APP_URL"] = "http://testserver"
        os.environ["ENVIRONMENT"] = "development"

        from fastapi.testclient import TestClient
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.jobs import process_job
        from app.main import app
        from app.models import Campaign, Job, Lead, SiteSetting

        with TestClient(app, follow_redirects=False) as client:
            response = client.get("/")
            assert response.status_code == 301
            assert response.headers["location"] == "/c/campaign-index"

            page = client.get("/c/campaign-index")
            assert page.status_code == 200
            assert "Download Gratis" in page.text
            assert "Independence Campaign Index" in page.text
            token = csrf(page.text)
            submitted = client.post("/c/campaign-index", data={
                "_csrf": token,
                "name": "Free User",
                "email": "free@example.com",
                "business_type": "Technology",
                "whatsapp": "081234567890",
                "consent": "on",
                "website": "",
            })
            assert submitted.status_code == 303
            access_url = submitted.headers["location"]
            with SessionLocal() as db:
                job = db.execute(select(Job).where(Job.status == "pending").order_by(Job.id)).scalars().first()
                process_job(db, job)
                job.status = "done"
                db.commit()
            ready = client.get(access_url)
            assert ready.status_code == 200
            assert "PASSWORD EXCEL" in ready.text
            assert "DOWNLOAD EXCEL" in ready.text

            # Turn seeded campaign into a paid product.
            with SessionLocal() as db:
                campaign = db.execute(select(Campaign).where(Campaign.slug == "campaign-index")).scalar_one()
                campaign.product_mode = "paid"
                campaign.price_amount = 99000
                campaign.checkout_url = "https://example.com/pay"
                campaign.payment_instructions = "Bayar dan cantumkan License ID."
                db.commit()

            paid_page = client.get("/c/campaign-index")
            assert "Rp99.000" in paid_page.text
            paid_token = csrf(paid_page.text)
            paid_submit = client.post("/c/campaign-index", data={
                "_csrf": paid_token,
                "name": "Paid User",
                "email": "paid@example.com",
                "business_type": "Retail",
                "whatsapp": "081234567891",
                "consent": "on",
                "website": "",
            })
            assert paid_submit.status_code == 303
            paid_access = paid_submit.headers["location"]
            pending = client.get(paid_access)
            assert "Selesaikan pembayaran" in pending.text
            assert "DOWNLOAD EXCEL" not in pending.text

            # Admin login and approve payment.
            login_page = client.get("/admin/login")
            login_token = csrf(login_page.text)
            login = client.post("/admin/login", data={"_csrf": login_token, "password": "admin-test"})
            assert login.status_code == 303
            dashboard = client.get("/admin")
            assert "Tandai Lunas" in dashboard.text
            admin_csrf = csrf(dashboard.text)
            with SessionLocal() as db:
                lead = db.execute(select(Lead).where(Lead.email == "paid@example.com")).scalar_one()
                lead_id = lead.id
            approved = client.post(f"/admin/leads/{lead_id}/mark-paid", data={"_csrf": admin_csrf})
            assert approved.status_code == 303
            with SessionLocal() as db:
                job = db.execute(select(Job).where(Job.status == "pending").order_by(Job.id.desc())).scalars().first()
                process_job(db, job)
                job.status = "done"
                db.commit()
                lead = db.get(Lead, lead_id)
                assert lead.payment_status == "paid"
                assert lead.status == "ready"
            paid_ready = client.get(paid_access)
            assert "PASSWORD EXCEL" in paid_ready.text
            assert "DOWNLOAD EXCEL" in paid_ready.text

            settings_page = client.get("/admin/settings")
            assert settings_page.status_code == 200
            assert "Disable katalog / single product" in settings_page.text
            with SessionLocal() as db:
                row = db.get(SiteSetting, 1)
                assert row.home_mode == "redirect"

        print("WEB FLOW TEST OK")


if __name__ == "__main__":
    main()
