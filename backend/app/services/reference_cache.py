"""In-process TTL cache for small, rarely-changing reference data.

retrieve_context used to re-scan the routes/stations/destinations/services tables
several times per chat turn. These tables are tiny and change only via admin edits,
so we cache the active rows per worker for a short TTL and let admin writes
invalidate explicitly. ORM rows are expunged so they're safe to read detached
(only mapped columns are accessed, never lazy relationships).
"""

import threading
import time
from collections.abc import Callable
from typing import Any

from app.config import get_settings
from app.database import SessionLocal
from app.models.models import Destination, Route, Service, Station

settings = get_settings()
_lock = threading.Lock()
_cache: dict[str, tuple[float, list[Any]]] = {}


def _get(key: str, loader: Callable[[], list[Any]]) -> list[Any]:
    now = time.monotonic()
    entry = _cache.get(key)
    if entry and entry[0] > now:
        return entry[1]
    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] > now:
            return entry[1]
        data = loader()
        _cache[key] = (now + settings.reference_cache_ttl, data)
        return data


def _load_active(model) -> list[Any]:
    db = SessionLocal()
    try:
        items = db.query(model).filter(model.is_active.is_(True)).all()
        db.expunge_all()  # detach so cached rows outlive the session safely
        return items
    finally:
        db.close()


def active_routes() -> list[Route]:
    return _get("routes", lambda: _load_active(Route))


def active_stations() -> list[Station]:
    return _get("stations", lambda: _load_active(Station))


def active_destinations() -> list[Destination]:
    return _get("destinations", lambda: _load_active(Destination))


def active_services() -> list[Service]:
    return _get("services", lambda: _load_active(Service))


def invalidate(*keys: str) -> None:
    """Drop cached entries (all if no keys given). Call from admin write paths."""
    with _lock:
        if not keys:
            _cache.clear()
        else:
            for k in keys:
                _cache.pop(k, None)
