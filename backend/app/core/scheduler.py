"""Daily maintenance scheduler.

Runs (across multiple workers, only one actually executes — guarded by a MySQL
advisory lock): refresh upcoming trips so the demo window never expires, purge old
logs (retention), and delete stale uploaded images.
"""

import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal, engine

logger = logging.getLogger(__name__)
settings = get_settings()
_scheduler: AsyncIOScheduler | None = None


def _refresh_trips() -> None:
    from app.seed.seed_demo_data import regenerate_all_trips
    from app.services.reference_cache import invalidate

    db = SessionLocal()
    try:
        created = regenerate_all_trips(db, days=settings.trip_refresh_days)
        invalidate()
        logger.info("Trip refresh: regenerated %d trips for %d days", created, settings.trip_refresh_days)
    finally:
        db.close()


def _purge_logs() -> None:
    from app.logs_database import get_logs_session_factory

    cutoff = datetime.utcnow() - timedelta(days=settings.log_retention_days)
    logs_db = get_logs_session_factory()()
    try:
        for table in ("chat_logs", "api_request_logs", "llm_call_logs", "auth_logs", "error_logs"):
            try:
                logs_db.execute(text(f"DELETE FROM {table} WHERE created_at < :cutoff"), {"cutoff": cutoff})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Log purge failed for %s: %s", table, exc)
        logs_db.commit()
        logger.info("Purged logs older than %d days", settings.log_retention_days)
    finally:
        logs_db.close()


def _purge_uploads() -> None:
    from app.services.chat_uploads import ensure_upload_dir

    cutoff = date.today() - timedelta(days=settings.upload_retention_days)
    removed = 0
    for f in ensure_upload_dir().glob("*"):
        try:
            if f.is_file() and date.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                removed += 1
        except Exception:  # noqa: BLE001
            pass
    if removed:
        logger.info("Removed %d uploads older than %d days", removed, settings.upload_retention_days)


def _run_maintenance() -> None:
    """One worker wins the lock and runs maintenance; the rest no-op."""
    with engine.connect() as conn:
        if conn.execute(text("SELECT GET_LOCK('gobus_maintenance', 0)")).scalar() != 1:
            return
        try:
            _refresh_trips()
            _purge_logs()
            _purge_uploads()
        finally:
            conn.execute(text("SELECT RELEASE_LOCK('gobus_maintenance')"))


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    # Daily at 00:10 UTC, plus once shortly after startup to self-heal an expired window.
    _scheduler.add_job(_run_maintenance, "cron", hour=0, minute=10, id="daily_maintenance")
    _scheduler.add_job(
        _run_maintenance, "date", run_date=datetime.utcnow() + timedelta(seconds=20), id="startup_maintenance"
    )
    _scheduler.start()
    logger.info("Maintenance scheduler started")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
