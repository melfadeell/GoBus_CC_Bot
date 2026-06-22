from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

_logs_engine = None
_logs_session_factory = None


class LogsBase(DeclarativeBase):
    pass


def get_logs_engine():
    global _logs_engine
    if _logs_engine is None:
        _logs_engine = create_engine(
            settings.logs_database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=30,
        )
    return _logs_engine


def get_logs_session_factory():
    global _logs_session_factory
    if _logs_session_factory is None:
        _logs_session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=get_logs_engine()
        )
    return _logs_session_factory


def get_logs_db():
    db = get_logs_session_factory()()
    try:
        yield db
    finally:
        db.close()
