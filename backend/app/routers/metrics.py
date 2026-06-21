from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.logs_database import get_logs_db
from app.logs_models import ApiRequestLog, AuthLog, ChatLog, ErrorLog, LlmCallLog
from app.models.models import AdminUser
from app.schemas.schemas import (
    ApiRequestLogOut,
    AuthLogOut,
    ChatLogOut,
    ErrorLogOut,
    LlmCallLogOut,
    MetricsCharts,
    MetricsDailyPoint,
    MetricsOverview,
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
    db: Session = Depends(get_logs_db),
    _: AdminUser = Depends(get_current_admin),
):
    start = date.today() - timedelta(days=days - 1)
    daily: list[MetricsDailyPoint] = []

    for offset in range(days):
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


@router.get("/chat-logs", response_model=PaginatedResponse[ChatLogOut])
def metrics_chat_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    channel: str | None = Query(None),
    session_id: str | None = Query(None),
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
