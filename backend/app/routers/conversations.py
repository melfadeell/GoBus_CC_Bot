from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.models import AdminUser, ChatMessage, ChatSession
from app.schemas.schemas import ChatMessageOut, ChatSessionOut, PaginatedResponse

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _filtered_sessions_query(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    min_messages: int | None = None,
):
    q = db.query(ChatSession)

    if date_from:
        q = q.filter(func.date(ChatSession.started_at) >= date_from)
    if date_to:
        q = q.filter(func.date(ChatSession.started_at) <= date_to)

    if min_messages is not None and min_messages > 0:
        matching_ids = (
            db.query(ChatMessage.session_id)
            .group_by(ChatMessage.session_id)
            .having(func.count(ChatMessage.id) >= min_messages)
        )
        q = q.filter(ChatSession.session_id.in_(matching_ids))

    return q


@router.get("", response_model=PaginatedResponse[ChatSessionOut])
def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    min_messages: int | None = Query(None, ge=0),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    q = _filtered_sessions_query(
        db, date_from=date_from, date_to=date_to, min_messages=min_messages
    )
    total = q.count()
    sessions = (
        q.order_by(ChatSession.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    session_ids = [s.session_id for s in sessions]
    counts: dict[str, int] = {}
    if session_ids:
        rows = (
            db.query(ChatMessage.session_id, func.count(ChatMessage.id))
            .filter(ChatMessage.session_id.in_(session_ids))
            .group_by(ChatMessage.session_id)
            .all()
        )
        counts = dict(rows)

    items = [
        ChatSessionOut(
            id=s.id,
            session_id=s.session_id,
            channel=s.channel,
            started_at=s.started_at,
            message_count=counts.get(s.session_id, 0),
        )
        for s in sessions
    ]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{session_id}/messages", response_model=list[ChatMessageOut])
def get_messages(
    session_id: str, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)
):
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="المحادثة غير موجودة")

    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
