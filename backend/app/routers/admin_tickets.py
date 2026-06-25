from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.core.constants import TICKET_AGENT_MESSAGE_KINDS, TICKET_PRIORITIES, TICKET_STATUSES
from app.database import get_db
from app.models.models import AdminUser, Ticket
from app.schemas.schemas import (
    PaginatedResponse,
    TicketAdminSummary,
    TicketOut,
    TicketReplyRequest,
    TicketUpdateRequest,
)
from app.services import ticket_service

router = APIRouter(
    prefix="/api/admin/tickets",
    tags=["admin-tickets"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=PaginatedResponse[TicketAdminSummary])
def list_tickets(
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    assigned_admin_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    q = db.query(Ticket)
    if status:
        q = q.filter(Ticket.status == status)
    if priority:
        q = q.filter(Ticket.priority == priority)
    if channel:
        q = q.filter(Ticket.channel == channel)
    if assigned_admin_id is not None:
        q = q.filter(Ticket.assigned_admin_id == assigned_admin_id)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Ticket.ref_number.like(like),
                Ticket.subject.like(like),
                Ticket.guest_email.like(like),
            )
        )

    total = q.count()
    rows = (
        q.order_by(Ticket.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse[TicketAdminSummary](
        items=rows, total=total, page=page, page_size=page_size
    )


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: int, payload: TicketUpdateRequest, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if payload.priority is not None:
        if payload.priority not in TICKET_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid priority")
        ticket_service.set_priority(db, ticket, payload.priority)
    if payload.assigned_admin_id is not None:
        ticket_service.assign(db, ticket, payload.assigned_admin_id or None)
    if payload.status is not None:
        if payload.status not in TICKET_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        ticket_service.set_status(db, ticket, payload.status)

    db.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/messages", response_model=TicketOut)
def reply(
    ticket_id: int,
    payload: TicketReplyRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if payload.kind not in TICKET_AGENT_MESSAGE_KINDS:
        raise HTTPException(status_code=400, detail="Invalid message kind")
    ticket_service.add_agent_message(
        db, ticket, body=payload.body, admin_id=admin.id, kind=payload.kind
    )
    db.refresh(ticket)
    return ticket
