from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.rate_limit import get_client_ip
from app.database import get_db
from app.models.models import AdminUser
from app.services.logs_writer import log_auth

security = HTTPBearer(auto_error=False)
settings = get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> AdminUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        email: str | None = payload.get("sub")
        if not email:
            raise _reject_token(request, "missing subject")
    except JWTError as exc:
        raise _reject_token(request, "invalid or expired token") from exc

    admin = db.query(AdminUser).filter(AdminUser.email == email).first()
    if not admin:
        raise _reject_token(request, "admin not found", email=email)
    return admin


def _reject_token(request: Request, reason: str, *, email: str = "unknown") -> HTTPException:
    """Log a rejected-token attempt and return the 401 to raise."""
    log_auth(
        email=email,
        action="token_rejected",
        client_ip=get_client_ip(request),
        status_code=401,
        success=False,
    )
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {reason}")
