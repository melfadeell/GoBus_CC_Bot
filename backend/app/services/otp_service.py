"""Email-OTP issue/verify for guest ticket creation & lookup.

Codes are 6-digit, stored hashed (sha256 keyed with the JWT secret), single-use,
with an expiry + attempt cap. A successful verify returns a short-lived signed
token that authorizes the guest action (create/lookup) for that email."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.models import EmailOtp
from app.services.email_service import otp_email, send_email

settings = get_settings()

_VERIFY_TOKEN_TTL_MINUTES = 20


def _hash_code(code: str) -> str:
    return hashlib.sha256(f"{settings.jwt_secret}:{code}".encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def issue_otp(db: Session, email: str, purpose: str = "ticket_create") -> None:
    """Generate a code, store its hash, and email it. Invalidates prior codes
    for the same (email, purpose)."""
    email = _normalize_email(email)
    db.query(EmailOtp).filter(
        EmailOtp.email == email,
        EmailOtp.purpose == purpose,
        EmailOtp.consumed == False,  # noqa: E712
    ).update({EmailOtp.consumed: True})

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_ttl_minutes)
    db.add(
        EmailOtp(
            email=email,
            code_hash=_hash_code(code),
            purpose=purpose,
            expires_at=expires_at,
        )
    )
    db.commit()

    subject, body = otp_email(code, settings.otp_ttl_minutes)
    send_email(email, subject, body)


def verify_otp(db: Session, email: str, code: str, purpose: str = "ticket_create") -> str | None:
    """Verify a code. On success returns a short-lived verified-email token,
    else None. Increments attempts and enforces the attempt cap."""
    email = _normalize_email(email)
    otp = (
        db.query(EmailOtp)
        .filter(
            EmailOtp.email == email,
            EmailOtp.purpose == purpose,
            EmailOtp.consumed == False,  # noqa: E712
        )
        .order_by(EmailOtp.created_at.desc())
        .first()
    )
    if otp is None:
        return None

    now = datetime.now(timezone.utc)
    expires_at = otp.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now or otp.attempts >= settings.otp_max_attempts:
        otp.consumed = True
        db.commit()
        return None

    otp.attempts += 1
    if not hmac.compare_digest(otp.code_hash, _hash_code(code)):
        db.commit()
        return None

    otp.consumed = True
    db.commit()
    return _create_verified_token(email, purpose)


def _create_verified_token(email: str, purpose: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_VERIFY_TOKEN_TTL_MINUTES)
    payload = {
        "sub": email,
        "typ": "email_verified",
        "purpose": purpose,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_verified_token(token: str, purpose: str = "ticket_create") -> str | None:
    """Return the verified email for a valid token of the given purpose, else None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("typ") != "email_verified" or payload.get("purpose") != purpose:
        return None
    return payload.get("sub")


def decode_verified_email(token: str) -> str | None:
    """Return the verified email for any valid email-verified token (purpose-agnostic).
    Used for guest ticket viewing, where a create- or lookup-purpose token both qualify."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("typ") != "email_verified":
        return None
    return payload.get("sub")
