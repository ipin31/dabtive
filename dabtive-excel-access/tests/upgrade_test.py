from __future__ import annotations
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / "old.db"
        connection = sqlite3.connect(db_path)
        connection.executescript("""
        CREATE TABLE campaigns (
          id INTEGER PRIMARY KEY, name VARCHAR(180), slug VARCHAR(100), active BOOLEAN,
          landing_title VARCHAR(220), landing_description TEXT, business_types TEXT,
          master_file VARCHAR(500), expiry_hours INTEGER, max_downloads INTEGER, created_at DATETIME
        );
        CREATE TABLE leads (
          id INTEGER PRIMARY KEY, campaign_id INTEGER, name VARCHAR(180), email VARCHAR(254),
          business_type VARCHAR(180), whatsapp VARCHAR(40), request_ip VARCHAR(80), user_agent VARCHAR(300),
          status VARCHAR(30), license_id VARCHAR(50), access_token VARCHAR(100), access_password_enc TEXT,
          error_message TEXT, created_at DATETIME, ready_at DATETIME
        );
        INSERT INTO campaigns VALUES (1,'Old Product','old-product',1,'Old','Description','Other',NULL,48,2,CURRENT_TIMESTAMP);
        INSERT INTO leads VALUES (1,1,'Old Lead','old@example.com','Other','6281',NULL,NULL,'ready','OLD-1','token','enc',NULL,CURRENT_TIMESTAMP,NULL);
        """)
        connection.commit(); connection.close()
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["DATA_DIR"] = str(Path(temp) / "data")
        from app.db import Base, SessionLocal, engine
        from app.migrations import run_lightweight_migrations
        from app.models import Campaign, Lead, SiteSetting
        Base.metadata.create_all(bind=engine)
        run_lightweight_migrations()
        with SessionLocal() as db:
            campaign = db.get(Campaign, 1)
            lead = db.get(Lead, 1)
            assert campaign.product_mode == "free"
            assert campaign.landing_body == ""
            assert lead.payment_status == "not_required"
            assert lead.payment_amount == 0
            db.add(SiteSetting(id=1, home_mode="redirect", home_campaign_id=1)); db.commit()
        print("UPGRADE TEST OK")


if __name__ == "__main__":
    main()
