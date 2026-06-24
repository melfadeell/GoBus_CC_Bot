from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import (
    create_customer_token,
    get_current_customer,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.core.rate_limit import get_client_ip, limiter
from app.database import get_db
from app.logs_database import get_logs_session_factory
from app.logs_models import AuthLog
from app.models.models import Customer
from app.schemas.schemas import (
    CustomerLoginRequest,
    CustomerMeResponse,
    CustomerPasswordRequest,
    CustomerRegisterRequest,
    CustomerUpdateRequest,
    TokenResponse,
)
from app.services.logs_writer import log_auth

router = APIRouter(prefix="/api/customer", tags=["customer-auth"])
settings = get_settings()


def _recent_failed_logins(email: str, client_ip: str | None) -> int:
    """Count failed customer logins for this email or IP within the lockout window."""
    since = datetime.now(timezone.utc) - timedelta(minutes=settings.login_lockout_window_minutes)
    logs_db = get_logs_session_factory()()
    try:
        q = logs_db.query(func.count(AuthLog.id)).filter(
            AuthLog.action == "customer_login_failed",
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


@router.post("/register", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_customer_auth)
def register(payload: CustomerRegisterRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.query(Customer).filter(Customer.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    customer = Customer(
        full_name=payload.full_name.strip(),
        phone=payload.phone.strip(),
        email=email,
        password_hash=hash_password(payload.password),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    log_auth(
        email=email,
        action="customer_register",
        client_ip=get_client_ip(request),
        status_code=200,
        success=True,
    )
    return TokenResponse(access_token=create_customer_token(customer.id))


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_customer_auth)
def login(payload: CustomerLoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = get_client_ip(request)
    email = payload.email.strip().lower()

    if _recent_failed_logins(email, client_ip) >= settings.login_lockout_threshold:
        log_auth(
            email=email,
            action="customer_login_locked",
            client_ip=client_ip,
            status_code=429,
            success=False,
        )
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")

    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer or not verify_password(payload.password, customer.password_hash):
        log_auth(
            email=email,
            action="customer_login_failed",
            client_ip=client_ip,
            status_code=401,
            success=False,
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    customer.last_login_at = datetime.now(timezone.utc)
    db.commit()
    log_auth(
        email=email,
        action="customer_login_success",
        client_ip=client_ip,
        status_code=200,
        success=True,
    )
    return TokenResponse(access_token=create_customer_token(customer.id))


@router.get("/me", response_model=CustomerMeResponse)
def me(customer: Customer = Depends(get_current_customer)):
    return customer


@router.put("/me", response_model=CustomerMeResponse)
def update_me(
    payload: CustomerUpdateRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    new_email = payload.email.strip().lower()
    if new_email != customer.email:
        taken = (
            db.query(Customer)
            .filter(Customer.email == new_email, Customer.id != customer.id)
            .first()
        )
        if taken:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
    customer.full_name = payload.full_name.strip()
    customer.phone = payload.phone.strip()
    customer.email = new_email
    db.commit()
    db.refresh(customer)
    return customer


@router.put("/password")
def change_password(
    payload: CustomerPasswordRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    if not verify_password(payload.old_password, customer.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    customer.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}
