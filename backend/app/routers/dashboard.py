from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.models import (
    AdminUser,
    ChatMessage,
    ChatSession,
    Destination,
    KbArticle,
    Station,
    Trip,
)
from app.schemas.schemas import (
    ChannelTokenStat,
    DailyAnalyticsPoint,
    DashboardAnalytics,
    DashboardStats,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _session_query(db: Session, channel: str | None):
    q = db.query(ChatSession)
    if channel:
        q = q.filter(ChatSession.channel == channel)
    return q


def _message_query(db: Session, channel: str | None):
    q = db.query(ChatMessage)
    if channel:
        q = q.join(ChatSession, ChatSession.session_id == ChatMessage.session_id).filter(
            ChatSession.channel == channel
        )
    return q


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    channel: str | None = Query(None),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    token_sum = _message_query(db, channel).with_entities(
        func.coalesce(func.sum(ChatMessage.total_tokens), 0)
    ).scalar()

    return DashboardStats(
        total_sessions=_session_query(db, channel).count(),
        total_messages=_message_query(db, channel).count(),
        total_tokens=int(token_sum or 0),
        kb_articles=db.query(KbArticle).count(),
        stations=db.query(Station).count(),
        destinations=db.query(Destination).count(),
        active_trips=db.query(Trip)
        .filter(Trip.trip_date >= date.today(), Trip.status == "open")
        .count(),
    )


@router.get("/analytics", response_model=DashboardAnalytics)
def get_analytics(
    channel: str | None = Query(None),
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    start = date.today() - timedelta(days=days - 1)

    by_channel: list[ChannelTokenStat] = []
    for ch_row in db.query(ChatSession.channel).distinct():
        ch = ch_row[0]
        if channel and ch != channel:
            continue
        sessions = db.query(ChatSession).filter(ChatSession.channel == ch).count()
        msg_q = (
            db.query(ChatMessage)
            .join(ChatSession, ChatSession.session_id == ChatMessage.session_id)
            .filter(ChatSession.channel == ch)
        )
        messages = msg_q.count()
        tokens = msg_q.with_entities(func.coalesce(func.sum(ChatMessage.total_tokens), 0)).scalar()
        by_channel.append(
            ChannelTokenStat(
                channel=ch,
                sessions=sessions,
                messages=messages,
                total_tokens=int(tokens or 0),
            )
        )

    by_channel.sort(key=lambda x: x.total_tokens, reverse=True)

    daily: list[DailyAnalyticsPoint] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        day_start = day.isoformat()
        msg_q = _message_query(db, channel).filter(func.date(ChatMessage.created_at) == day)
        messages = msg_q.count()
        tokens = msg_q.with_entities(func.coalesce(func.sum(ChatMessage.total_tokens), 0)).scalar()
        daily.append(
            DailyAnalyticsPoint(
                date=day_start,
                messages=messages,
                tokens=int(tokens or 0),
            )
        )

    return DashboardAnalytics(by_channel=by_channel, daily=daily)
