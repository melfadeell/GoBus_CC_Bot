from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.core.constants import estimate_cost_usd
from app.database import get_db
from app.logs_database import get_logs_session_factory
from app.logs_models import ChatLog
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

# Seeded demo analytics use synthetic (mock) token counts; exclude them so token
# totals reflect real chat usage only. Session/message counts still include demo.
DEMO_SESSION_PREFIX = "demo-%"
MAX_RANGE_DAYS = 92


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _resolve_window(
    days: int, date_from: str | None, date_to: str | None
) -> tuple[date, date]:
    """Return an inclusive [start, end] window from explicit dates or a day count."""
    df, dt = _parse_date(date_from), _parse_date(date_to)
    if df and dt:
        if dt < df:
            df, dt = dt, df
        if (dt - df).days + 1 > MAX_RANGE_DAYS:
            df = dt - timedelta(days=MAX_RANGE_DAYS - 1)
        return df, dt
    end = date.today()
    return end - timedelta(days=days - 1), end


def _real_token_split(msg_query) -> tuple[int, int, int]:
    """(total, prompt, completion) tokens excluding seeded demo sessions."""
    row = (
        msg_query.filter(~ChatMessage.session_id.like(DEMO_SESSION_PREFIX))
        .with_entities(
            func.coalesce(func.sum(ChatMessage.total_tokens), 0),
            func.coalesce(func.sum(ChatMessage.prompt_tokens), 0),
            func.coalesce(func.sum(ChatMessage.completion_tokens), 0),
        )
        .one()
    )
    return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)


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


def _apply_msg_dates(q, date_from: date | None, date_to: date | None):
    if date_from:
        q = q.filter(func.date(ChatMessage.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(ChatMessage.created_at) <= date_to)
    return q


def _cost_from_logs(
    channel: str | None, date_from: date | None, date_to: date | None
) -> tuple[float, dict[str, float]]:
    """Estimated USD cost from the logs DB (ChatLog has model + token split).

    ChatLog holds only real chat turns (no seeded demo rows), so cost is
    inherently real. Returns (total_cost, {date_iso: cost}).
    """
    logs_db = get_logs_session_factory()()
    try:
        q = logs_db.query(
            func.date(ChatLog.created_at),
            ChatLog.model,
            func.coalesce(func.sum(ChatLog.prompt_tokens), 0),
            func.coalesce(func.sum(ChatLog.completion_tokens), 0),
        )
        if channel:
            q = q.filter(ChatLog.channel == channel)
        if date_from:
            q = q.filter(func.date(ChatLog.created_at) >= date_from)
        if date_to:
            q = q.filter(func.date(ChatLog.created_at) <= date_to)
        q = q.group_by(func.date(ChatLog.created_at), ChatLog.model)

        per_day: dict[str, float] = {}
        total = 0.0
        for day_val, model, pt, ct in q.all():
            cost = estimate_cost_usd(model, int(pt or 0), int(ct or 0))
            key = day_val.isoformat() if hasattr(day_val, "isoformat") else str(day_val)
            per_day[key] = per_day.get(key, 0.0) + cost
            total += cost
        return round(total, 4), per_day
    finally:
        logs_db.close()


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    channel: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    df, dt = _parse_date(date_from), _parse_date(date_to)

    sessions_q = _session_query(db, channel)
    messages_q = _message_query(db, channel)
    if df:
        sessions_q = sessions_q.filter(func.date(ChatSession.started_at) >= df)
        messages_q = _apply_msg_dates(messages_q, df, None)
    if dt:
        sessions_q = sessions_q.filter(func.date(ChatSession.started_at) <= dt)
        messages_q = _apply_msg_dates(messages_q, None, dt)

    total_tokens, prompt_tokens, completion_tokens = _real_token_split(
        _apply_msg_dates(_message_query(db, channel), df, dt)
    )
    total_cost, _ = _cost_from_logs(channel, df, dt)

    return DashboardStats(
        total_sessions=sessions_q.count(),
        total_messages=messages_q.count(),
        total_tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_cost_usd=total_cost,
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
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    start, end = _resolve_window(days, date_from, date_to)

    by_channel: list[ChannelTokenStat] = []
    for ch_row in db.query(ChatSession.channel).distinct():
        ch = ch_row[0]
        if channel and ch != channel:
            continue
        sessions = db.query(ChatSession).filter(ChatSession.channel == ch).count()
        msg_q = _apply_msg_dates(
            db.query(ChatMessage)
            .join(ChatSession, ChatSession.session_id == ChatMessage.session_id)
            .filter(ChatSession.channel == ch),
            start,
            end,
        )
        total, prompt, completion = _real_token_split(msg_q)
        by_channel.append(
            ChannelTokenStat(
                channel=ch,
                sessions=sessions,
                messages=msg_q.count(),
                total_tokens=total,
                prompt_tokens=prompt,
                completion_tokens=completion,
            )
        )

    by_channel.sort(key=lambda x: x.total_tokens, reverse=True)

    _, cost_by_day = _cost_from_logs(channel, start, end)

    daily: list[DailyAnalyticsPoint] = []
    span = (end - start).days
    for offset in range(span + 1):
        day = start + timedelta(days=offset)
        day_iso = day.isoformat()
        msg_q = _apply_msg_dates(_message_query(db, channel), day, day)
        total, prompt, completion = _real_token_split(msg_q)
        daily.append(
            DailyAnalyticsPoint(
                date=day_iso,
                messages=msg_q.count(),
                tokens=total,
                prompt_tokens=prompt,
                completion_tokens=completion,
                cost_usd=round(cost_by_day.get(day_iso, 0.0), 4),
            )
        )

    return DashboardAnalytics(by_channel=by_channel, daily=daily)
