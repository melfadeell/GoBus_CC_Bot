from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin, verify_password
from app.config import get_settings
from app.core.rate_limit import get_client_ip, limiter
from app.database import get_db
from app.logs_database import get_logs_session_factory
from app.logs_models import AuthLog
from app.models.models import AdminUser
from app.schemas.schemas import LoginRequest, TokenResponse
from app.services.logs_writer import log_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _recent_failed_logins(email: str, client_ip: str | None) -> int:
    """Count failed logins for this email or IP within the lockout window."""
    since = datetime.now(timezone.utc) - timedelta(minutes=settings.login_lockout_window_minutes)
    logs_db = get_logs_session_factory()()
    try:
        q = logs_db.query(func.count(AuthLog.id)).filter(
            AuthLog.action == "login_failed",
            AuthLog.created_at >= since,
        )
        cond = AuthLog.email == email
        if client_ip:
            cond = cond | (AuthLog.client_ip == client_ip)
        return int(q.filter(cond).scalar() or 0)
    except Exception:
        return 0
    finally:
        logs_db.close()


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_auth)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = get_client_ip(request)

    # Temporary lockout after repeated failures (per email/IP within the window).
    if _recent_failed_logins(payload.email, client_ip) >= settings.login_lockout_threshold:
        log_auth(
            email=payload.email,
            action="login_locked",
            client_ip=client_ip,
            status_code=429,
            success=False,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again later.",
        )

    admin = db.query(AdminUser).filter(AdminUser.email == payload.email).first()
    if not admin or not verify_password(payload.password, admin.password_hash):
        log_auth(
            email=payload.email,
            action="login_failed",
            client_ip=client_ip,
            status_code=401,
            success=False,
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(admin.email)
    log_auth(
        email=payload.email,
        action="login_success",
        client_ip=client_ip,
        status_code=200,
        success=True,
    )
    return TokenResponse(access_token=token)


@router.get("/me")
def me(admin: AdminUser = Depends(get_current_admin)):
    return {"email": admin.email, "id": admin.id}
