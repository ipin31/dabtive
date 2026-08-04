from __future__ import annotations
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def csrf(html: str) -> str:
    match = re.search(r'name="_csrf" value="([^"]+)"', html)
    assert match
    return match.group(1)


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        os.environ["DATABASE_URL"] = f"sqlite:///{root / 'test.db'}"
        os.environ["DATA_DIR"] = str(root / "data")
        os.environ["SECRET_KEY"] = "gallery-test-secret-key-abcdefghijklmnopqrstuvwxyz"
        os.environ["ADMIN_PASSWORD"] = "admin-test"
        os.environ["APP_URL"] = "http://testserver"
        os.environ["ENVIRONMENT"] = "development"

        from fastapi.testclient import TestClient
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.main import app
        from app.models import Campaign, CampaignImage

        png_1 = (Path(__file__).resolve().parents[1] / "seed" / "campaign-preview-1.png").read_bytes()
        png_2 = (Path(__file__).resolve().parents[1] / "seed" / "campaign-preview-2.png").read_bytes()

        with TestClient(app, follow_redirects=False) as client:
            login_page = client.get("/admin/login")
            logged = client.post("/admin/login", data={"_csrf": csrf(login_page.text), "password": "admin-test"})
            assert logged.status_code == 303

            new_page = client.get("/admin/campaigns/new")
            token = csrf(new_page.text)
            response = client.post(
                "/admin/campaigns/new",
                data={
                    "_csrf": token,
                    "name": "Gallery Product",
                    "slug": "gallery-product",
                    "landing_title": "Gallery Product",
                    "landing_description": "Description",
                    "landing_body": "Body",
                    "highlights": "Feature one\nFeature two",
                    "business_types": "Retail\nOther",
                    "expiry_hours": "48",
                    "max_downloads": "2",
                    "active": "on",
                    "price_amount": "0",
                    "purchase_button_label": "BELI SEKARANG",
                },
                files=[
                    ("gallery_images", ("one.png", png_1, "image/png")),
                    ("gallery_images", ("two.png", png_2, "image/png")),
                ],
            )
            assert response.status_code == 303, response.text

            with SessionLocal() as db:
                campaign = db.execute(select(Campaign).where(Campaign.slug == "gallery-product")).scalar_one()
                images = db.execute(select(CampaignImage).where(CampaignImage.campaign_id == campaign.id).order_by(CampaignImage.sort_order)).scalars().all()
                assert len(images) == 2
                campaign_id = campaign.id
                first_id = images[0].id

            page = client.get("/c/gallery-product")
            assert page.status_code == 200
            assert page.text.count("data-slide") == 2
            image_response = client.get(f"/media/campaigns/{campaign_id}/images/{first_id}")
            assert image_response.status_code == 200
            assert image_response.headers["content-type"].startswith("image/png")

            detail = client.get(f"/admin/campaigns/{campaign_id}")
            deleted = client.post(
                f"/admin/campaigns/{campaign_id}/images/{first_id}/delete",
                data={"_csrf": csrf(detail.text)},
            )
            assert deleted.status_code == 303
            with SessionLocal() as db:
                count = len(db.execute(select(CampaignImage).where(CampaignImage.campaign_id == campaign_id)).scalars().all())
                assert count == 1

        print("GALLERY TEST OK")


if __name__ == "__main__":
    main()
