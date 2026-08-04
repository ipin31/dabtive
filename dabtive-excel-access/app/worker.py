from __future__ import annotations
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.jobs import process_job
from app.migrations import run_lightweight_migrations
from app.models import Download, Job, Lead

settings = get_settings()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def cleanup_expired() -> None:
    with SessionLocal() as db:
        expired_downloads = db.execute(select(Download).where(Download.expires_at <= utcnow())).scalars().all()
        for item in expired_downloads:
            if item.file_path:
                Path(item.file_path).unlink(missing_ok=True)
                item.file_path = None
        db.commit()


def run() -> None:
    settings.data_path
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    last_cleanup = 0.0
    while True:
        if time.monotonic() - last_cleanup >= settings.cleanup_interval_seconds:
            cleanup_expired()
            last_cleanup = time.monotonic()

        db = SessionLocal()
        try:
            now = utcnow()
            job = db.execute(
                select(Job)
                .where(Job.status == "pending", Job.available_at <= now)
                .order_by(Job.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).scalar_one_or_none()
            if not job:
                db.close()
                time.sleep(settings.job_poll_seconds)
                continue
            job.status = "running"
            job.locked_at = now
            job.attempts += 1
            db.commit()
            try:
                process_job(db, job)
                job = db.get(Job, job.id)
                job.status = "done"
                job.finished_at = utcnow()
                job.last_error = None
                db.commit()
            except Exception as exc:
                db.rollback()
                job = db.get(Job, job.id)
                lead_id = job.payload.get("lead_id") if job else None
                if lead_id:
                    lead = db.get(Lead, lead_id)
                    if lead:
                        lead.status = "failed"
                        lead.error_message = str(exc)[:1000]
                job.last_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}"
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    job.finished_at = utcnow()
                else:
                    job.status = "pending"
                    job.available_at = utcnow() + timedelta(seconds=min(300, 10 * (2 ** (job.attempts - 1))))
                db.commit()
                print(f"Job {job.id} failed: {exc}")
        finally:
            db.close()


if __name__ == "__main__":
    run()
