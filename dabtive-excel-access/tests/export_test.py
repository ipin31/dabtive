from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.leads_export import build_leads_xlsx


def main() -> None:
    data = build_leads_xlsx([
        {
            "created_at": "03 Aug 2026, 23:16 WIB",
            "name": "Yusuf Fikri",
            "whatsapp": "628123456789",
            "email": "yusuf@example.com",
            "business_type": "Digital Agency",
            "campaign": "Independence Campaign Index",
            "license_id": "DAB-260803-000001",
            "payment_status": "paid",
            "payment_amount": 99000,
            "status": "ready",
            "downloads": 1,
            "expires_at": "05 Aug 2026, 23:16 WIB",
        }
    ], "03 Aug 2026, 23:16 WIB")
    assert data[:2] == b"PK"
    with ZipFile(BytesIO(data)) as workbook:
        names = set(workbook.namelist())
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/styles.xml" in names
        sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "Yusuf Fikri" in sheet
        assert "628123456789" in sheet
        assert "DABTIVE LEADS DATABASE" in sheet
        assert 'autoFilter ref="A4:L5"' in sheet
    print("EXPORT TEST OK", len(data))


if __name__ == "__main__":
    main()
