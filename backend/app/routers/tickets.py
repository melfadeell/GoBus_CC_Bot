from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_customer_optional
from app.config import get_settings
from app.core.constants import (
    DEFAULT_CHAT_CHANNEL,
    DEFAULT_TICKET_PRIORITY,
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
)
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.models import Customer
from app.schemas.schemas import (
    OtpRequestRequest,
    OtpVerifyRequest,
    OtpVerifyResponse,
    TicketCreateRequest,
    TicketMessageOut,
    TicketOut,
    TicketReplyRequest,
    TicketSummary,
)
from app.services import ticket_service
from app.services.otp_service import (
    decode_verified_email,
    decode_verified_token,
    issue_otp,
    verify_otp,
)
from fastapi import Request

router = APIRouter(prefix="/api/tickets", tags=["tickets"])
settings = get_settings()


def _validate_category(category: str) -> str:
    return category if category in TICKET_CATEGORIES else "other"


def _validate_priority(priority: str | None) -> str:
    return priority if priority in TICKET_PRIORITIES else DEFAULT_TICKET_PRIORITY


# --- Guest email verification (OTP) ---------------------------------------

@router.post("/otp/request")
@limiter.limit(settings.rate_limit_otp_request)
def request_otp(payload: OtpRequestRequest, request: Request, db: Session = Depends(get_db)):
    issue_otp(db, payload.email, payload.purpose)
    return {"sent": True}


@router.post("/otp/verify", response_model=OtpVerifyResponse)
@limiter.limit(settings.rate_limit_ticket)
def verify_otp_code(payload: OtpVerifyRequest, request: Request, db: Session = Depends(get_db)):
    token = verify_otp(db, payload.email, payload.code, payload.purpose)
    if not token:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    return OtpVerifyResponse(verified_token=token)


# --- Create / list / view -------------------------------------------------

def _to_customer_ticket(ticket) -> TicketOut:
    """Customer-facing ticket view — hides internal agent comments."""
    out = TicketOut.model_validate(ticket)
    out.messages = [
        TicketMessageOut.model_validate(m) for m in ticket_service.customer_visible_messages(ticket)
    ]
    return out


@router.post("", response_model=TicketOut)
@limiter.limit(settings.rate_limit_ticket)
def create_ticket(
    payload: TicketCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer_optional),
):
    channel = payload.channel or DEFAULT_CHAT_CHANNEL
    category = _validate_category(payload.category)
    # Priority is normally set by the ticketing agent; fall back to default.
    priority = _validate_priority(payload.priority)
    priority_auto = _validate_priority(payload.priority_auto or payload.priority)

    if customer is None:
        # Guest path: require name + phone + an OTP-verified email matching guest_email.
        if not (payload.guest_name and payload.guest_email and payload.guest_phone):
            raise HTTPException(
                status_code=400,
                detail="Guests must provide name, email, and phone.",
            )
        verified_email = (
            decode_verified_token(payload.verified_token, "ticket_create")
            if payload.verified_token
            else None
        )
        if not verified_email or verified_email != payload.guest_email.strip().lower():
            raise HTTPException(
                status_code=401,
                detail="Email not verified. Verify the OTP sent to your email first.",
            )

    ticket = ticket_service.create_ticket(
        db,
        subject=payload.subject,
        description=payload.description,
        category=category,
        priority=priority,
        priority_auto=priority_auto,
        channel=channel,
        customer=customer,
        guest_name=None if customer else payload.guest_name,
        guest_email=None if customer else payload.guest_email,
        guest_phone=None if customer else payload.guest_phone,
        session_id=payload.session_id,
    )
    return _to_customer_ticket(ticket)


@router.get("", response_model=list[TicketSummary])
def list_my_tickets(
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer_optional),
):
    if customer is None:
        raise HTTPException(status_code=401, detail="Login required to list tickets")
    return ticket_service.list_for_customer(db, customer.id)


@router.get("/{ref}", response_model=TicketOut)
def get_ticket(
    ref: str,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer_optional),
    verified_token: str | None = Query(default=None),
):
    ticket = ticket_service.get_by_ref(db, ref)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _authorize_ticket_access(ticket, customer, verified_token)
    return _to_customer_ticket(ticket)


@router.post("/{ref}/messages", response_model=TicketOut)
def reply_to_ticket(
    ref: str,
    payload: TicketReplyRequest,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer_optional),
    verified_token: str | None = Query(default=None),
):
    ticket = ticket_service.get_by_ref(db, ref)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _authorize_ticket_access(ticket, customer, verified_token)
    ticket_service.add_message(
        db,
        ticket,
        author_type="customer",
        body=payload.body,
        author_id=customer.id if customer else None,
    )
    db.refresh(ticket)
    return _to_customer_ticket(ticket)


def _authorize_ticket_access(ticket, customer, verified_token) -> None:
    """Allow the owning customer, or a guest with an OTP-verified token matching
    the ticket's guest email. Raises 403 otherwise."""
    if customer is not None and ticket.customer_id == customer.id:
        return
    if ticket.customer_id is None and verified_token:
        email = decode_verified_email(verified_token)
        if email and ticket.guest_email and email == ticket.guest_email:
            return
    raise HTTPException(status_code=403, detail="Not allowed to view this ticket")
