import logging
from typing import Any

from app.logs_database import get_logs_session_factory
from app.logs_models import ApiRequestLog, AuthLog, ChatLog, ErrorLog, LlmCallLog

logger = logging.getLogger(__name__)
MAX_TEXT_LENGTH = 4000


def _truncate(value: str | None, max_len: int = MAX_TEXT_LENGTH) -> str | None:
    if value is None:
        return None
    if len(value) <= max_len:
        return value
    return value[:max_len] + "...[truncated]"


def _session():
    return get_logs_session_factory()()


def log_request_start(
    request_id: str,
    method: str,
    path: str,
    *,
    client_ip: str | None = None,
) -> None:
    try:
        db = _session()
        try:
            db.add(
                ApiRequestLog(
                    request_id=request_id,
                    api_method=method,
                    api_path=path,
                    client_ip=client_ip,
                    success=False,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to write request start log: %s", exc)


def log_request_end(
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    response_time_sec: float,
    *,
    client_ip: str | None = None,
    error_message: str | None = None,
) -> None:
    try:
        db = _session()
        try:
            db.add(
                ApiRequestLog(
                    request_id=request_id,
                    api_method=method,
                    api_path=path,
                    client_ip=client_ip,
                    status_code=status_code,
                    response_time_sec=response_time_sec,
                    success=200 <= status_code < 400,
                    error_message=_truncate(error_message),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to write request end log: %s", exc)


def log_chat_turn(
    *,
    request_id: str | None,
    session_id: str,
    channel: str | None,
    client_ip: str | None,
    user_message: str,
    ai_response: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    response_time_sec: float,
    has_image: bool,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    try:
        db = _session()
        try:
            db.add(
                ChatLog(
                    request_id=request_id,
                    session_id=session_id,
                    channel=channel,
                    client_ip=client_ip,
                    user_message=_truncate(user_message),
                    ai_response=_truncate(ai_response),
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    response_time_sec=response_time_sec,
                    has_image=has_image,
                    success=success,
                    error_message=_truncate(error_message),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to write chat log: %s", exc)


def log_llm_call(
    *,
    request_id: str | None,
    session_id: str | None,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    response_time_sec: float,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    try:
        db = _session()
        try:
            db.add(
                LlmCallLog(
                    request_id=request_id,
                    session_id=session_id,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    response_time_sec=response_time_sec,
                    success=success,
                    error_message=_truncate(error_message),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to write LLM log: %s", exc)


def log_auth(
    *,
    email: str,
    action: str,
    client_ip: str | None,
    status_code: int,
    success: bool,
) -> None:
    try:
        db = _session()
        try:
            db.add(
                AuthLog(
                    email=email,
                    action=action,
                    client_ip=client_ip,
                    status_code=status_code,
                    success=success,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to write auth log: %s", exc)


def log_error(
    *,
    request_id: str | None,
    error_type: str,
    message: str | None,
    stack_trace: str | None = None,
) -> None:
    try:
        db = _session()
        try:
            db.add(
                ErrorLog(
                    request_id=request_id,
                    error_type=error_type,
                    message=_truncate(message, 8000),
                    stack_trace=_truncate(stack_trace, 8000),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to write error log: %s", exc)
