"""Ensure MySQL databases exist and bootstrap tables."""

import logging
from urllib.parse import unquote

import pymysql
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, SessionLocal, engine

logger = logging.getLogger(__name__)
settings = get_settings()


def ensure_mysql_database(database_url: str | None = None) -> None:
    """Create the MySQL database if it does not exist."""
    url = make_url(database_url or settings.database_url)
    database = url.database
    if not database:
        logger.warning("No database name in DATABASE_URL — skipping database creation")
        return

    host = url.host or "localhost"
    port = url.port or 3306
    user = url.username or "root"
    password = unquote(url.password) if url.password else ""

    connection = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        connection.commit()
        logger.info("Database '%s' is ready", database)
    finally:
        connection.close()


def is_database_seeded(db: Session) -> bool:
    """True when initial data was already loaded (admin account exists)."""
    from app.models.models import AdminUser

    return db.query(AdminUser).count() > 0


def bootstrap_logs_database() -> None:
    """Create logs DB and tables."""
    from app.logs_database import LogsBase, get_logs_engine
    import app.logs_models  # noqa: F401 — register models

    ensure_mysql_database(settings.logs_database_url)
    LogsBase.metadata.create_all(bind=get_logs_engine())
    logger.info("Logs database tables are ready")


def bootstrap_database() -> None:
    """
    Startup hook (safe with multiple workers — guarded by a MySQL advisory lock so
    only one worker runs DDL/migrations/seed; the others wait then no-op):
    1. Create MySQL databases if missing
    2. Create all tables + run migrations
    3. Seed website data on first run only
    """
    ensure_mysql_database(settings.database_url)
    bootstrap_logs_database()

    # Serialize schema/seed work across workers with GET_LOCK.
    with engine.connect() as conn:
        got = conn.execute(
            text("SELECT GET_LOCK('gobus_bootstrap', 30)")
        ).scalar()
        if got != 1:
            logger.warning("Could not acquire bootstrap lock; skipping (another worker is handling it)")
            return
        try:
            _run_bootstrap_steps()
        finally:
            conn.execute(text("SELECT RELEASE_LOCK('gobus_bootstrap')"))


def _run_bootstrap_steps() -> None:
    from app.core.migrations import run_migrations
    from app.seed.seed_website_data import seed_initial_data

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables are ready")

    run_migrations(engine)

    db = SessionLocal()
    try:
        if is_database_seeded(db):
            logger.info("Database already seeded — skipping initial import")
            return
        logger.info("First run detected — seeding initial data...")
        seed_initial_data(db)
        logger.info("Initial seed completed successfully")
    finally:
        db.close()
