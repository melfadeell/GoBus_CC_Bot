from contextlib import asynccontextmanager
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
from app.core.rate_limit import get_client_ip, limiter
from app.routers import (
    auth,
    bot_settings,
    chat,
    conversations,
    dashboard,
    destinations,
    kb,
    metrics,
    services,
    stations,
    trips,
)
from app.services.logs_writer import log_error, log_request_end

settings = get_settings()
logger = logging.getLogger(__name__)


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
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_database()
    yield


app = FastAPI(title="GoBus Chatbot API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_request: Request, _exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded: maximum 15 chat messages per minute per IP."},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiLoggingMiddleware)

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
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(auth.router)
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
    return {"status": "ok"}
