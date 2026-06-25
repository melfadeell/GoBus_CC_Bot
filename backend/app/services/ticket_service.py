"""Ticket CRM domain logic: creation, lookup, thread messages, status workflow,
and the customer email notifications (created / resolved).

Email sending is dispatched on a daemon thread so it never blocks the request
(SMTP has a network timeout; in mock mode it's instant)."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import threading

from sqlalchemy.orm import Session

from app.core.constants import DEFAULT_HOTLINE
from app.models.models import BotSettings, Customer, Ticket, TicketMessage
from app.services.email_service import (
    send_email,
    ticket_agent_reply_email,
    ticket_created_email,
    ticket_resolved_email,
)


def _hotline(db: Session) -> str:
    """The single source of truth for the hotline — the editable BotSettings row."""
    bot = db.query(BotSettings).first()
    return (bot.hotline if bot and bot.hotline else DEFAULT_HOTLINE)


def _fire_email(
    to: str | None,
    subject: str,
    text: str,
    html: str | None = None,
    *,
    no_reply: bool = False,
) -> None:
    if not to:
        return
    threading.Thread(
        target=send_email,
        kwargs={"to": to, "subject": subject, "body_text": text, "body_html": html, "no_reply": no_reply},
        daemon=True,
    ).start()


def _recipient(ticket: Ticket) -> str | None:
    if ticket.customer is not None:
        return ticket.customer.email
    return ticket.guest_email


def _recipient_name(ticket: Ticket) -> str | None:
    if ticket.customer is not None:
        return ticket.customer.full_name
    return ticket.guest_name


def _lang_for(ticket: Ticket) -> str:
    """Pick the email language from the customer's own words (Arabic vs English)."""
    sample = f"{ticket.subject} {ticket.description}"
    return "ar" if re.search(r"[؀-ۿ]", sample) else "en"


def generate_ref_number(year: int, ticket_id: int) -> str:
    return f"GB-{year}-{ticket_id:06d}"


def create_ticket(
    db: Session,
    *,
    subject: str,
    description: str,
    category: str = "other",
    priority: str = "medium",
    priority_auto: str | None = None,
    channel: str = "website",
    customer: Customer | None = None,
    guest_name: str | None = None,
    guest_email: str | None = None,
    guest_phone: str | None = None,
    session_id: str | None = None,
) -> Ticket:
    """Create a ticket + its opening message, then notify the customer by email."""
    ticket = Ticket(
        ref_number="",  # set after flush so we can embed the id
        customer_id=customer.id if customer else None,
        guest_name=guest_name,
        guest_email=(guest_email.strip().lower() if guest_email else None),
        guest_phone=guest_phone,
        channel=channel,
        category=category,
        subject=subject.strip(),
        description=description.strip(),
        status="open",
        priority=priority,
        priority_auto=priority_auto or priority,
        session_id=session_id,
    )
    db.add(ticket)
    db.flush()  # assigns ticket.id
    year = ticket.created_at.year if ticket.created_at else datetime.now(timezone.utc).year
    ticket.ref_number = generate_ref_number(year, ticket.id)

    db.add(
        TicketMessage(
            ticket_id=ticket.id,
            author_type="customer" if customer or guest_email else "system",
            author_id=customer.id if customer else None,
            body=description.strip(),
        )
    )
    db.commit()
    db.refresh(ticket)

    subj, text, html = ticket_created_email(
        ticket.ref_number,
        ticket.subject,
        ticket.category,
        _recipient_name(ticket),
        _hotline(db),
        _lang_for(ticket),
    )
    _fire_email(_recipient(ticket), subj, text, html)
    return ticket


def list_for_customer(db: Session, customer_id: int) -> list[Ticket]:
    return (
        db.query(Ticket)
        .filter(Ticket.customer_id == customer_id)
        .order_by(Ticket.created_at.desc())
        .all()
    )


def get_by_ref(db: Session, ref_number: str) -> Ticket | None:
    return db.query(Ticket).filter(Ticket.ref_number == ref_number).first()


def add_message(
    db: Session,
    ticket: Ticket,
    *,
    author_type: str,
    body: str,
    author_id: int | None = None,
    attachment_url: str | None = None,
) -> TicketMessage:
    msg = TicketMessage(
        ticket_id=ticket.id,
        author_type=author_type,
        author_id=author_id,
        body=body.strip(),
        attachment_url=attachment_url,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def add_agent_message(
    db: Session,
    ticket: Ticket,
    *,
    body: str,
    admin_id: int,
    kind: str = "reply",
) -> TicketMessage:
    """Add an agent thread entry. ``reply`` emails the customer (no-reply); ``comment`` is internal."""
    author_type = "agent_comment" if kind == "comment" else "agent"
    msg = add_message(
        db,
        ticket,
        author_type=author_type,
        body=body,
        author_id=admin_id,
    )
    if kind == "reply":
        subj, text, html = ticket_agent_reply_email(
            ticket.ref_number,
            ticket.subject,
            body,
            _recipient_name(ticket),
            _hotline(db),
            _lang_for(ticket),
        )
        _fire_email(_recipient(ticket), subj, text, html, no_reply=True)
    return msg


def customer_visible_messages(ticket: Ticket) -> list[TicketMessage]:
    """Thread messages shown to the customer (hides internal agent comments)."""
    return [m for m in ticket.messages if m.author_type != "agent_comment"]


def set_status(db: Session, ticket: Ticket, status: str) -> Ticket:
    """Update status; on transition to 'resolved' stamp resolved_at + email the customer."""
    was_resolved = ticket.status == "resolved"
    ticket.status = status
    if status == "resolved":
        ticket.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    if status == "resolved" and not was_resolved:
        subj, text, html = ticket_resolved_email(
            ticket.ref_number, ticket.subject, _recipient_name(ticket), _hotline(db), _lang_for(ticket)
        )
        _fire_email(_recipient(ticket), subj, text, html)
    return ticket


def set_priority(db: Session, ticket: Ticket, priority: str) -> Ticket:
    ticket.priority = priority
    db.commit()
    db.refresh(ticket)
    return ticket


def assign(db: Session, ticket: Ticket, admin_id: int | None) -> Ticket:
    ticket.assigned_admin_id = admin_id
    db.commit()
    db.refresh(ticket)
    return ticket
