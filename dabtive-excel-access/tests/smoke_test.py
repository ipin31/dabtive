from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test.db")
os.environ.setdefault("DATA_DIR", "./data")

from app.services.files import encrypt_excel_file, verify_excel_password


def main() -> None:
    source = Path("seed/dabtive-campaign-index-demo.xlsx")
    if not source.exists():
        raise SystemExit("Demo master file not found")
    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp) / "protected.xlsx"
        password = "DAB-Test-92K!"
        created = Path(encrypt_excel_file(source, output, password))
        assert created.exists() and created.stat().st_size > 0
        assert created.read_bytes()[:8] == bytes.fromhex("D0CF11E0A1B11AE1")
        verify_excel_password(str(created), password)
        print("SMOKE TEST OK", created.stat().st_size)


if __name__ == "__main__":
    main()
