from contextlib import asynccontextmanager
import asyncio
import logging
import time
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.core.bootstrap import bootstrap_database
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.rate_limit import get_client_ip, limiter
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.routers import (
    admin_tickets,
    auth,
    bot_settings,
    chat,
    conversations,
    customer_auth,
    dashboard,
    destinations,
    kb,
    metrics,
    services,
    stations,
    tickets,
    trips,
)
from app.services.logs_writer import log_error, log_request_end

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        return response


class ApiLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        client_ip = get_client_ip(request)
        started = time.perf_counter()

        response = await call_next(request)
        elapsed = time.perf_counter() - started
        log_request_end(
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            client_ip=client_ip,
        )
        # Record server errors that weren't already captured by the unhandled
        # exception handler (which logs full stack traces).
        if response.status_code >= 500 and not getattr(request.state, "error_logged", False):
            log_error(
                request_id=request_id,
                error_type=f"HTTP{response.status_code}",
                message=f"{request.method} {request.url.path} -> {response.status_code}",
            )
        return response


def _warn_weak_secrets() -> None:
    if settings.jwt_secret in ("dev-secret-change-me", "gobus-dev-jwt-secret-change-in-production"):
        logger.warning("JWT_SECRET is a known default — set a strong random secret in production.")
    if settings.admin_password == "admin123":
        logger.warning("ADMIN_PASSWORD is the default 'admin123' — change it before production.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warn_weak_secrets()
    bootstrap_database()
    from app.services.openai_client import get_openai_client
    from app.services.reference_cache import (
        active_destinations,
        active_routes,
        active_services,
        active_stations,
    )

    get_openai_client()
    await asyncio.to_thread(
        lambda: (
            active_routes(),
            active_stations(),
            active_destinations(),
            active_services(),
        )
    )
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="GoBus Chatbot API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_request: Request, _exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded ({settings.rate_limit_chat} per IP). Please slow down."},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.add_middleware(ApiLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

register_exception_handlers(app)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    log_error(
        request_id=request_id,
        error_type=type(exc).__name__,
        message=str(exc),
        stack_trace=traceback.format_exc(),
    )
    # Mark so the logging middleware doesn't double-log this as a generic 5xx.
    request.state.error_logged = True
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(auth.router)
app.include_router(customer_auth.router)
app.include_router(tickets.router)
app.include_router(admin_tickets.router)
app.include_router(kb.router)
app.include_router(stations.router)
app.include_router(destinations.router)
app.include_router(trips.router)
app.include_router(services.router)
app.include_router(bot_settings.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(dashboard.router)
app.include_router(metrics.router)


@app.get("/api/health")
def health():
    """Deep health check: verifies both databases are reachable."""
    from sqlalchemy import text as _sql_text

    from app.database import engine as main_engine
    from app.logs_database import get_logs_engine

    checks: dict[str, str] = {}
    for name, eng in (("database", main_engine), ("logs_database", get_logs_engine())):
        try:
            with eng.connect() as conn:
                conn.execute(_sql_text("SELECT 1"))
            checks[name] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks[name] = f"error: {type(exc).__name__}"

    healthy = all(v == "ok" for v in checks.values())
    body = {
        "status": "ok" if healthy else "degraded",
        "version": settings.app_version,
        "checks": checks,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=body)
