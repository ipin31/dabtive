from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Dabtive Excel Access"
    app_url: str = "http://localhost:8000"
    secret_key: str = "development-secret-change-me"
    admin_password: str = "admin"
    environment: str = "development"
    timezone: str = "Asia/Jakarta"

    database_url: str = "postgresql+psycopg://dabtive:dabtive@db:5432/dabtive"
    data_dir: str = "./data"
    max_upload_mb: int = 50
    job_poll_seconds: float = 2.0
    cleanup_interval_seconds: int = 300
    rate_limit_email_per_hour: int = 3
    rate_limit_ip_per_hour: int = 12

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "access@example.com"
    smtp_from_name: str = "Dabtive"
    smtp_use_tls: bool = True

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "uploads").mkdir(parents=True, exist_ok=True)
        (path / "generated").mkdir(parents=True, exist_ok=True)
        (path / "images").mkdir(parents=True, exist_ok=True)
        return path

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_email)


@lru_cache
def get_settings() -> Settings:
    return Settings()
