from __future__ import annotations
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

OLE_ENCRYPTED_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def safe_filename(value: str) -> str:
    result = "".join(char if char.isalnum() or char in "-_" else "-" for char in value)
    return result.strip("-")[:90] or "file"


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_helper(args: list[str], timeout: int = 180) -> None:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    system_python = Path("/usr/bin/python3")
    helper = Path(__file__).with_name("libreoffice_encrypt.py")
    if not soffice:
        raise RuntimeError("LibreOffice tidak terpasang di server")
    if not system_python.exists():
        raise RuntimeError("/usr/bin/python3 tidak tersedia untuk python3-uno")

    port = _free_local_port()
    with tempfile.TemporaryDirectory(prefix="dabtive-lo-") as profile:
        office = subprocess.Popen(
            [
                soffice, "--headless", "--nologo", "--nodefault", "--nofirststartwizard",
                "--norestore", "--nolockcheck", f"-env:UserInstallation={Path(profile).resolve().as_uri()}",
                f"--accept=socket,host=127.0.0.1,port={port};urp;StarOffice.ServiceManager",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        try:
            command = [str(system_python), str(helper), *args, "--port", str(port)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "Unknown LibreOffice error")[-2000:]
                raise RuntimeError(f"Gagal memproses proteksi Excel: {detail}")
        finally:
            office.terminate()
            try:
                office.wait(timeout=10)
            except subprocess.TimeoutExpired:
                office.kill()
                office.wait(timeout=5)


def encrypt_excel_file(master: Path, output: Path, password: str) -> str:
    if master.suffix.lower() != ".xlsx":
        raise ValueError("Master file harus berformat .xlsx")
    output = output.with_suffix(".xlsx")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{time.time_ns()}.tmp.xlsx")
    try:
        _run_helper(["encrypt", str(master.resolve()), str(temporary.resolve()), "--password", password])
        if not temporary.exists() or temporary.stat().st_size == 0:
            raise RuntimeError("File Excel terenkripsi tidak terbentuk")
        with temporary.open("rb") as handle:
            if handle.read(8) != OLE_ENCRYPTED_SIGNATURE:
                raise RuntimeError("Output tidak terdeteksi sebagai Excel terenkripsi")
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return str(output)


def verify_excel_password(file_path: str, password: str) -> None:
    _run_helper(["verify", str(Path(file_path).resolve()), "--password", password])
