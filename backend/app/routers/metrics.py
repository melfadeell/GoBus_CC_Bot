from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.logs_database import get_logs_db
from app.logs_models import ApiRequestLog, AuthLog, ChatLog, ErrorLog, LlmCallLog
from app.models.models import AdminUser, Customer, Ticket
from app.schemas.schemas import (
    ApiRequestLogOut,
    AuthLogOut,
    ChatLogOut,
    ErrorLogOut,
    LlmCallLogOut,
    MetricsCharts,
    MetricsDailyPoint,
    MetricsOverview,
    MetricsUserStat,
    PaginatedResponse,
)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _apply_created_filter(query, model, date_from: date | None, date_to: date | None):
    if date_from:
        query = query.filter(func.date(model.created_at) >= date_from)
    if date_to:
        query = query.filter(func.date(model.created_at) <= date_to)
    return query


@router.get("/overview", response_model=MetricsOverview)
def metrics_overview(
    days: int = Query(30, ge=7, le=90),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_logs_db),
    _: AdminUser = Depends(get_current_admin),
):
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    if not parsed_from and not parsed_to:
        parsed_from = date.today() - timedelta(days=days - 1)
        parsed_to = date.today()

    req_q = _apply_created_filter(db.query(ApiRequestLog), ApiRequestLog, parsed_from, parsed_to)
    chat_q = _apply_created_filter(db.query(ChatLog), ChatLog, parsed_from, parsed_to)
    llm_q = _apply_created_filter(db.query(LlmCallLog), LlmCallLog, parsed_from, parsed_to)
    err_q = _apply_created_filter(db.query(ErrorLog), ErrorLog, parsed_from, parsed_to)

    avg_latency = req_q.with_entities(func.avg(ApiRequestLog.response_time_sec)).scalar()
    token_sum = chat_q.with_entities(func.coalesce(func.sum(ChatLog.total_tokens), 0)).scalar()
    rate_limit_hits = req_q.filter(ApiRequestLog.status_code == 429).count()

    return MetricsOverview(
        total_requests=req_q.count(),
        chat_turns=chat_q.count(),
        llm_calls=llm_q.count(),
        errors=err_q.count(),
        rate_limit_hits=rate_limit_hits,
        avg_latency_sec=round(float(avg_latency or 0), 3),
        total_tokens=int(token_sum or 0),
        date_from=parsed_from.isoformat() if parsed_from else None,
        date_to=parsed_to.isoformat() if parsed_to else None,
    )


@router.get("/charts", response_model=MetricsCharts)
def metrics_charts(
    days: int = Query(30, ge=7, le=90),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_logs_db),
    _: AdminUser = Depends(get_current_admin),
):
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    if parsed_from and parsed_to:
        if parsed_to < parsed_from:
            parsed_from, parsed_to = parsed_to, parsed_from
        start = parsed_from
        span = min((parsed_to - parsed_from).days, 92)
    else:
        start = date.today() - timedelta(days=days - 1)
        span = days - 1

    daily: list[MetricsDailyPoint] = []

    for offset in range(span + 1):
        day = start + timedelta(days=offset)
        day_str = day.isoformat()

        requests = (
            db.query(ApiRequestLog)
            .filter(func.date(ApiRequestLog.created_at) == day)
            .count()
        )
        chat_turns = (
            db.query(ChatLog).filter(func.date(ChatLog.created_at) == day).count()
        )
        tokens = (
            db.query(ChatLog)
            .filter(func.date(ChatLog.created_at) == day)
            .with_entities(func.coalesce(func.sum(ChatLog.total_tokens), 0))
            .scalar()
        )
        errors = (
            db.query(ErrorLog).filter(func.date(ErrorLog.created_at) == day).count()
        )
        rate_limits = (
            db.query(ApiRequestLog)
            .filter(
                func.date(ApiRequestLog.created_at) == day,
                ApiRequestLog.status_code == 429,
            )
            .count()
        )

        daily.append(
            MetricsDailyPoint(
                date=day_str,
                requests=requests,
                chat_turns=chat_turns,
                tokens=int(tokens or 0),
                errors=errors,
                rate_limit_hits=rate_limits,
            )
        )

    return MetricsCharts(daily=daily)


@router.get("/requests", response_model=PaginatedResponse[ApiRequestLogOut])
def metrics_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    path: str | None = Query(None),
    status: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_logs_db),
    _: AdminUser = Depends(get_current_admin),
):
    query = db.query(ApiRequestLog)
    if path:
        query = query.filter(ApiRequestLog.api_path.contains(path))
    if status is not None:
        query = query.filter(ApiRequestLog.status_code == status)
    query = _apply_created_filter(query, ApiRequestLog, _parse_date(date_from), _parse_date(date_to))

    total = query.count()
    items = (
        query.order_by(ApiRequestLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/users", response_model=PaginatedResponse[MetricsUserStat])
def metrics_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_logs_db),
    main_db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """Per-customer traceability: chat activity (logs DB) + ticket counts + profile
    (main DB), for logged-in customers (customer_id present on the chat turn)."""
    q = (
        db.query(
            ChatLog.customer_id,
            func.max(ChatLog.customer_email).label("email"),
            func.count(ChatLog.id).label("turns"),
            func.coalesce(func.sum(ChatLog.total_tokens), 0).label("tokens"),
            func.max(ChatLog.created_at).label("last_seen"),
        )
        .filter(ChatLog.customer_id.isnot(None))
        .group_by(ChatLog.customer_id)
    )
    q = _apply_created_filter(q, ChatLog, _parse_date(date_from), _parse_date(date_to))
    q = q.order_by(func.max(ChatLog.created_at).desc())

    rows = q.all()
    total = len(rows)
    page_rows = rows[(page - 1) * page_size : (page - 1) * page_size + page_size]

    cust_ids = [r[0] for r in page_rows]
    profiles = {
        c.id: c
        for c in main_db.query(Customer).filter(Customer.id.in_(cust_ids)).all()
    } if cust_ids else {}
    ticket_counts = dict(
        main_db.query(Ticket.customer_id, func.count(Ticket.id))
        .filter(Ticket.customer_id.in_(cust_ids))
        .group_by(Ticket.customer_id)
        .all()
    ) if cust_ids else {}

    items = [
        MetricsUserStat(
            customer_id=cid,
            customer_email=email,
            full_name=profiles[cid].full_name if cid in profiles else None,
            chat_turns=int(turns or 0),
            total_tokens=int(tokens or 0),
            tickets=int(ticket_counts.get(cid, 0)),
            last_seen=last_seen,
        )
        for (cid, email, turns, tokens, last_seen) in page_rows
    ]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/users/{customer_id}")
def metrics_user_detail(
    customer_id: int,
    db: Session = Depends(get_logs_db),
    main_db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    """Full activity trace for one customer: profile + totals + recent chats + tickets."""
    customer = main_db.query(Customer).filter(Customer.id == customer_id).first()

    agg = (
        db.query(
            func.count(ChatLog.id),
            func.coalesce(func.sum(ChatLog.total_tokens), 0),
            func.count(func.distinct(ChatLog.session_id)),
            func.min(ChatLog.created_at),
            func.max(ChatLog.created_at),
        )
        .filter(ChatLog.customer_id == customer_id)
        .one()
    )
    recent_chats = (
        db.query(ChatLog)
        .filter(ChatLog.customer_id == customer_id)
        .order_by(ChatLog.created_at.desc())
        .limit(20)
        .all()
    )

    tickets = (
        main_db.query(Ticket)
        .filter(Ticket.customer_id == customer_id)
        .order_by(Ticket.created_at.desc())
        .all()
    )
    by_status: dict[str, int] = {}
    for tk in tickets:
        by_status[tk.status] = by_status.get(tk.status, 0) + 1

    return {
        "customer": {
            "id": customer.id if customer else customer_id,
            "full_name": customer.full_name if customer else None,
            "email": customer.email if customer else None,
            "phone": customer.phone if customer else None,
            "created_at": customer.created_at.isoformat() if customer and customer.created_at else None,
            "last_login_at": customer.last_login_at.isoformat()
            if customer and customer.last_login_at
            else None,
        },
        "chat_turns": int(agg[0] or 0),
        "total_tokens": int(agg[1] or 0),
        "sessions": int(agg[2] or 0),
        "first_seen": agg[3].isoformat() if agg[3] else None,
        "last_seen": agg[4].isoformat() if agg[4] else None,
        "tickets_total": len(tickets),
        "tickets_by_status": by_status,
        "recent_chats": [
            {
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "channel": r.channel,
                "user_message": (r.user_message or "")[:200],
                "ai_response": (r.ai_response or "")[:200],
                "total_tokens": r.total_tokens,
                "success": r.success,
            }
            for r in recent_chats
        ],
        "recent_tickets": [
            {
                "ref_number": tk.ref_number,
                "subject": tk.subject,
                "status": tk.status,
                "priority": tk.priority,
                "created_at": tk.created_at.isoformat() if tk.created_at else None,
            }
            for tk in tickets[:20]
        ],
    }


@router.get("/chat-logs", response_model=PaginatedResponse[ChatLogOut])
def metrics_chat_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    channel: str | None = Query(None),
    session_id: str | None = Query(None),
    customer_email: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_logs_db),
    _: AdminUser = Depends(get_current_admin),
):
    query = db.query(ChatLog)
    if channel:
        query = query.filter(ChatLog.channel == channel)
    if session_id:
        query = query.filter(ChatLog.session_id == session_id)
    if customer_email:
        query = query.filter(ChatLog.customer_email.like(f"%{customer_email.strip()}%"))
    query = _apply_created_filter(query, ChatLog, _parse_date(date_from), _parse_date(date_to))

    total = query.count()
    items = (
        query.order_by(ChatLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/llm-calls", response_model=PaginatedResponse[LlmCallLogOut])
def metrics_llm_calls(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_logs_db),
    _: AdminUser = Depends(get_current_admin),
):
    query = _apply_created_filter(
        db.query(LlmCallLog), LlmCallLog, _parse_date(date_from), _parse_date(date_to)
    )
    total = query.count()
    items = (
        query.order_by(LlmCallLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/auth-logs", response_model=PaginatedResponse[AuthLogOut])
def metrics_auth_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_logs_db),
    _: AdminUser = Depends(get_current_admin),
):
    query = _apply_created_filter(
        db.query(AuthLog), AuthLog, _parse_date(date_from), _parse_date(date_to)
    )
    total = query.count()
    items = (
        query.order_by(AuthLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/errors", response_model=PaginatedResponse[ErrorLogOut])
def metrics_errors(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_logs_db),
    _: AdminUser = Depends(get_current_admin),
):
    query = _apply_created_filter(
        db.query(ErrorLog), ErrorLog, _parse_date(date_from), _parse_date(date_to)
    )
    total = query.count()
    items = (
        query.order_by(ErrorLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
