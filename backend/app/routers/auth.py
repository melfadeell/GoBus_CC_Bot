from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin, verify_password
from app.core.rate_limit import get_client_ip
from app.database import get_db
from app.models.models import AdminUser
from app.schemas.schemas import LoginRequest, TokenResponse
from app.services.logs_writer import log_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = get_client_ip(request)
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
