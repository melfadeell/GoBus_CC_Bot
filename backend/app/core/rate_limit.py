import logging

from fastapi import Request
from slowapi import Limiter

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _build_limiter() -> Limiter:
    """Use Redis for cross-worker limits when reachable; else in-memory per-worker.

    Multiple uvicorn workers each have their own in-memory limiter, so the limit is
    only correct cluster-wide when backed by Redis. We probe Redis at startup and
    fall back gracefully so local dev (no Redis) still works.
    """
    url = (settings.redis_url or "").strip()
    if url:
        try:
            import redis

            redis.Redis.from_url(url, socket_connect_timeout=1).ping()
            logger.info("Rate limiter using Redis at %s", url)
            return Limiter(key_func=get_client_ip, storage_uri=url)
        except Exception as exc:  # noqa: BLE001 - any redis failure → fallback
            logger.warning("Redis unavailable (%s); rate limiter falling back to in-memory", exc)
    return Limiter(key_func=get_client_ip)


limiter = _build_limiter()
