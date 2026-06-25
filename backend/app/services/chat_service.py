import asyncio
from collections.abc import AsyncGenerator, Callable
import re
import time

from openai import OpenAIError
from sqlalchemy.orm import Session

from app.services.openai_client import get_openai_client

from app.config import get_settings
from app.core.constants import (
    CHAT_CHANNELS,
    DEFAULT_CHAT_CHANNEL,
    DEFAULT_GREETING_AR,
    DEFAULT_HOTLINE,
    DEFAULT_SYSTEM_PROMPT,
)
from app.core.guardrails import HARD_GUARDRAILS
from app.core.logging import metrics_logger
from app.models.models import BotSettings, ChatMessage, ChatSession, Ticket
from app.services.chat_understanding import ChatUnderstanding, understand_message
from app.services.kb_retrieval import _HISTORY_SEP, retrieve_context
from app.services.logs_writer import log_chat_turn, log_error, log_llm_call
from app.services.query_understanding import correct_query, needs_rewrite
from app.services.ticketing_agent import build_ticket_draft

settings = get_settings()


class ChatProcessingError(Exception):
    """Raised when chat cannot be completed."""


def normalize_channel(channel: str | None) -> str:
    if not channel:
        return DEFAULT_CHAT_CHANNEL
    normalized = channel.strip().lower()
    if normalized == "web":
        return "website"
    if normalized in CHAT_CHANNELS:
        return normalized
    return DEFAULT_CHAT_CHANNEL


def get_or_create_session(db: Session, session_id: str, channel: str | None = None) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        session = ChatSession(session_id=session_id, channel=normalize_channel(channel))
        db.add(session)
        db.flush()
    return session


def get_bot_settings(db: Session) -> BotSettings:
    bot = db.query(BotSettings).first()
    if not bot:
        bot = BotSettings(
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            greeting_ar=DEFAULT_GREETING_AR,
            hotline=DEFAULT_HOTLINE,
            model_name=settings.openai_model,
        )
        db.add(bot)
        db.flush()
    return bot


def get_conversation_history(
    db: Session,
    session_id: str,
    *,
    user_limit: int = 5,
    assistant_limit: int = 5,
) -> list[dict]:
    """Short memory: last N user + last N assistant messages (10 total max)."""
    users = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.role == "user")
        .order_by(ChatMessage.created_at.desc())
        .limit(user_limit)
        .all()
    )
    assistants = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at.desc())
        .limit(assistant_limit)
        .all()
    )
    combined = sorted(users + assistants, key=lambda m: m.created_at)
    return [{"role": m.role, "content": m.content} for m in combined if m.content.strip()]


def fetch_ticket_summaries(db: Session, customer_id: int, limit: int = 10) -> list[dict]:
    """Compact ticket rows for the chat follow-up cards (plain dicts so nothing
    detached is accessed from the async context)."""
    rows = (
        db.query(Ticket)
        .filter(Ticket.customer_id == customer_id)
        .order_by(Ticket.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "ref_number": t.ref_number,
            "subject": t.subject,
            "category": t.category,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


def _reply_language_directive(message: str) -> str:
    """Per-message language instruction — far more reliable than a general rule."""
    if re.search(r"[؀-ۿ]", message or ""):
        return (
            "\n--- Language (mandatory) ---\n"
            "The user's message is in Arabic. Reply entirely in Arabic. "
            "Label any map link [افتح الخريطة](URL).\n"
        )
    if re.search(r"[A-Za-z]", message or ""):
        return (
            "\n--- Language (mandatory) ---\n"
            "The user's message is in English. Reply entirely in English, including any "
            "table headers (Station | Address | Working hours | Map). Keep stored Arabic "
            "names/addresses as-is. Label any map link [Open map](URL), never 'افتح الخريطة'.\n"
        )
    return ""


_TICKET_DIRECTIVES = {
    "raise_collect": (
        "\n--- Support ticket (mandatory) ---\n"
        "The customer wants to raise a complaint/ticket but has NOT yet described what "
        "actually happened. Do NOT create a ticket and do NOT show any form. Reply with "
        "ONE short, friendly question asking them to describe the problem (what happened, "
        "when, which trip/route if relevant) so you can open the ticket for them.\n"
    ),
    "raise": (
        "\n--- Support ticket (mandatory) ---\n"
        "The customer described their issue. The app is showing them a ticket form "
        "(pre-filled) to review and confirm — do NOT ask for the details again and "
        "do NOT claim a ticket was created. Reply with ONE short line telling them to review "
        "and confirm the ticket details shown below.\n"
    ),
    "check": (
        "\n--- Support ticket (mandatory) ---\n"
        "The customer is following up on their tickets. The app is showing their tickets as "
        "cards below. Reply with ONE short line (e.g. 'Here are your tickets:'); do NOT list "
        "or invent ticket details yourself.\n"
    ),
    "login_required": (
        "\n--- Support ticket (mandatory) ---\n"
        "The customer asked about their tickets but is not logged in. Politely ask them to log "
        "in (or create an account) to view their tickets. Keep it to one or two short lines.\n"
    ),
}

_STRUCTURED_DIRECTIVES = {
    "trips_shown": (
        "\n--- Live trip results (mandatory) ---\n"
        "The app is ALREADY showing the customer a trips table with dates, times, class, "
        "seats, and prices in EGP directly below your reply. The data exists and is visible.\n"
        "Reply with ONLY one short intro line (e.g. \"Here are the trips from Cairo to "
        "Hurghada:\" / \"إليك رحلات القاهرة–الغردقة:\").\n"
        "FORBIDDEN: saying you cannot provide prices/schedules, telling them to check the "
        "app or website for prices, or claiming you lack trip data. The table IS the answer.\n"
    ),
    "stations_shown": (
        "\n--- Live station card (mandatory) ---\n"
        "Station details (address, hours, map) are ALREADY shown as a card below your reply. "
        "Reply with ONE short intro line only. NEVER say you can't provide the address or "
        "to check the app — the card already shows it.\n"
    ),
    "destinations_shown": (
        "\n--- Live destinations list (mandatory) ---\n"
        "Destination chips are ALREADY shown below your reply. Reply with ONE short intro "
        "line only. Do NOT list destinations yourself.\n"
    ),
    "kb_from_context": (
        "\n--- KB answer (mandatory) ---\n"
        "The GoBus knowledge-base context below contains the official answer to this question. "
        "Answer from that context using Markdown bullets/headers. Do NOT say you lack specific "
        "details, and do NOT give only generic advice when [FAQ] or [Services] blocks already "
        "answer the question. Do NOT show or mention a trips table — this is not a schedule query.\n"
    ),
}


def _build_system_prompt(
    system_prompt: str,
    context: str,
    message: str = "",
    ticket_mode: str | None = None,
    structured_mode: str | None = None,
    hotline: str = DEFAULT_HOTLINE,
) -> str:
    formatting = """
--- Response format (mandatory) ---
Use Markdown: ## headers for sections, - bullets for lists. No wall-of-text paragraphs.
Short paragraphs only.

--- Structured results (mandatory) ---
Trips, stations, and the destinations list are rendered to the user automatically as
tables/cards/chips by the app. When the KB context says these are "shown to the user",
reply with ONLY a short one-line intro and do NOT repeat, list, or re-format that data
yourself. Never invent trips/stations/prices, and never claim you lack data when the
context says results are shown.
"""
    ticket_directive = _TICKET_DIRECTIVES.get(ticket_mode or "", "")
    structured_directive = _STRUCTURED_DIRECTIVES.get(structured_mode or "", "")
    kb_context = (
        context
        if context
        else "No GoBus-specific KB matches for this query. General questions may still be answered helpfully."
    )
    assembled = f"""{HARD_GUARDRAILS}

{system_prompt}
{formatting}{ticket_directive}{structured_directive}
{_reply_language_directive(message)}
--- سياق قاعدة المعرفة (GoBus) ---
{kb_context}
"""
    # Single-source hotline: the prompt/guardrails carry a {{HOTLINE}} placeholder
    # that we fill from the editable BotSettings.hotline at runtime.
    return assembled.replace("{{HOTLINE}}", hotline)


def _build_user_content(message: str, ocr_text: str | None = None) -> str:
    parts: list[str] = []
    if message.strip():
        parts.append(message.strip())
    if ocr_text is not None:
        if ocr_text.strip():
            parts.append(
                "--- Text extracted from customer image (OCR) ---\n" + ocr_text.strip()
            )
        else:
            parts.append(
                "--- Customer uploaded an image but no readable text was detected (OCR) ---"
            )
    return "\n\n".join(parts)


def _prepare_turn(
    db: Session, session_id: str, channel: str, stored_content: str, image_url: str | None
) -> dict:
    """Sync pre-LLM DB work (runs in a thread): persist the user message, load
    bot settings + short history. Returns plain values so nothing detached is
    accessed later from the async context."""
    get_or_create_session(db, session_id, channel)
    db.add(ChatMessage(session_id=session_id, role="user", content=stored_content, image_url=image_url))
    db.flush()
    bot = get_bot_settings(db)
    history = get_conversation_history(db, session_id)
    return {
        "system_prompt": bot.system_prompt,
        "model_name": bot.model_name or settings.openai_model,
        "history": history,
        "hotline": bot.hotline or DEFAULT_HOTLINE,
    }


def _finalize_turn(
    db: Session,
    session_id: str,
    full_response: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    """Sync post-LLM DB work (runs in a thread): persist the assistant message."""
    if full_response.strip():
        db.add(
            ChatMessage(
                session_id=session_id,
                role="assistant",
                content=full_response.strip(),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
        )
    db.commit()


def _fire(fn: Callable, **kwargs) -> None:
    """Run a (sync) logging write off the event loop, fire-and-forget."""
    try:
        asyncio.create_task(asyncio.to_thread(fn, **kwargs))
    except RuntimeError:
        fn(**kwargs)


async def stream_chat_response(
    db: Session,
    session_id: str,
    user_message: str,
    *,
    ocr_text: str | None = None,
    image_url: str | None = None,
    channel: str | None = None,
    client_ip: str | None = None,
    request_id: str | None = None,
    cancelled: Callable[[], bool] | None = None,
    customer_id: int | None = None,
    customer_name: str | None = None,
    customer_email: str | None = None,
) -> AsyncGenerator[dict, None]:
    if not settings.openai_api_key:
        raise ChatProcessingError("OpenAI API key is not configured")

    started = time.perf_counter()
    normalized_channel = normalize_channel(channel)
    stored_content = _build_user_content(user_message, ocr_text)

    # Pre-LLM DB work runs in a thread so it never blocks the event loop.
    prep = await asyncio.to_thread(
        _prepare_turn, db, session_id, normalized_channel, stored_content, image_url
    )
    system_prompt = prep["system_prompt"]
    model_name = prep["model_name"]
    history = prep["history"]
    hotline = prep.get("hotline", DEFAULT_HOTLINE)

    # Recent turns (excluding the message just stored) let trip retrieval resolve
    # follow-ups that don't name a route, e.g. "the latest 5 trips".
    history_text = _HISTORY_SEP.join(
        m["content"] for m in history if m["content"] != stored_content
    )
    raw_query = user_message or (ocr_text or "")

    # LLM understands message + conversation context to decide routing (replaces
    # keyword/regex intent detection). Also produces a normalized search query.
    understanding: ChatUnderstanding = await understand_message(raw_query, history=history)
    corrected_query = understanding.search_query
    if (
        not settings.chat_understanding_enabled
        and raw_query
        and needs_rewrite(raw_query)
    ):
        corrected_query = await correct_query(raw_query, history_text)

    ticket_mode: str | None = None
    ticket_meta: dict | None = None
    skip_structured = understanding.in_complaint_flow

    retrieval_debug: dict = {}
    context = await asyncio.to_thread(
        retrieve_context,
        db,
        raw_query,
        10,
        debug=retrieval_debug,
        history_text=history_text,
        extra_query=corrected_query if corrected_query.strip() != raw_query.strip() else None,
        skip_structured=skip_structured,
        understanding=understanding,
    )
    has_content_result = bool(
        retrieval_debug.get("trips")
        or retrieval_debug.get("stations")
        or retrieval_debug.get("destinations")
    )
    in_raise_flow = understanding.ticket_intent == "raise" or (
        understanding.continue_complaint_flow and not has_content_result
    )
    if in_raise_flow:
        draft = await build_ticket_draft(history, raw_query)
        if draft.get("ready"):
            # Enough detail — show the pre-filled confirm form.
            ticket_mode = "raise"
            ticket_meta = {
                "type": "meta",
                "action": "open_ticket_form",
                "draft": draft,
                "logged_in": customer_id is not None,
                "channel": normalized_channel,
            }
        else:
            # Not enough detail yet — the bot asks what the problem is first.
            ticket_mode = "raise_collect"
    elif understanding.ticket_intent == "check":
        if customer_id is not None:
            ticket_mode = "check"
            tickets_list = await asyncio.to_thread(fetch_ticket_summaries, db, customer_id)
            ticket_meta = {"type": "meta", "tickets_crm": tickets_list}
        else:
            ticket_mode = "login_required"
            ticket_meta = {"type": "meta", "action": "login_required"}

    structured_mode: str | None = None
    if retrieval_debug.get("trips"):
        structured_mode = "trips_shown"
    elif retrieval_debug.get("stations"):
        structured_mode = "stations_shown"
    elif retrieval_debug.get("destinations"):
        structured_mode = "destinations_shown"
    elif understanding.wants_service_info or (
        understanding.booking_related and not understanding.wants_live_trips
    ):
        structured_mode = "kb_from_context"

    messages = [
        {
            "role": "system",
            "content": _build_system_prompt(
                system_prompt, context, raw_query, ticket_mode, structured_mode, hotline
            ),
        }
    ]
    messages.extend(history)

    if ticket_meta is not None:
        yield ticket_meta

    # Surface the trips SQL only when debug exposure is explicitly enabled
    # (off in production — never leak internal SQL/schema to public chat users).
    trips_sql = retrieval_debug.get("trips_sql")
    if trips_sql and settings.expose_sql_debug:
        yield {"type": "meta", "sql": trips_sql}

    # Structured KB cards/tables are suppressed during ticket flows so a complaint
    # question never picks up an unrelated station/destination by accident.
    if ticket_mode is None:
        stations = retrieval_debug.get("stations")
        if stations:
            yield {"type": "meta", "stations": stations}

        destinations = retrieval_debug.get("destinations")
        if destinations:
            yield {"type": "meta", "destinations": destinations}

        trips = retrieval_debug.get("trips")
        if trips:
            yield {"type": "meta", "trips": trips}

    client = get_openai_client()
    full_response = ""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    log_error_msg: str | None = None

    create_kwargs: dict = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    # GPT-5 / reasoning models only accept the default temperature; sending a
    # custom value returns a 400. Other models keep the tuned low temperature.
    if not model_name.lower().startswith(("gpt-5", "o1", "o3", "o4")):
        create_kwargs["temperature"] = 0.3

    try:
        stream = await client.chat.completions.create(**create_kwargs)

        async for chunk in stream:
            if cancelled and cancelled():
                await asyncio.to_thread(db.rollback)
                return

            if getattr(chunk, "usage", None):
                prompt_tokens = chunk.usage.prompt_tokens or 0
                completion_tokens = chunk.usage.completion_tokens or 0
                total_tokens = chunk.usage.total_tokens or 0

            if not chunk.choices:
                continue
            delta = getattr(chunk.choices[0].delta, "content", None)
            if delta:
                if not full_response:
                    # Report time-to-first-token (from request receipt) once.
                    yield {
                        "type": "meta",
                        "ttft_ms": int((time.perf_counter() - started) * 1000),
                    }
                full_response += delta
                yield {"type": "token", "content": delta}

    except OpenAIError as exc:
        await asyncio.to_thread(db.rollback)
        log_error_msg = str(exc)
        elapsed = time.perf_counter() - started
        _fire(
            log_chat_turn,
            request_id=request_id,
            session_id=session_id,
            channel=normalized_channel,
            client_ip=client_ip,
            user_message=stored_content,
            ai_response="",
            model=model_name,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            response_time_sec=elapsed,
            has_image=bool(image_url),
            success=False,
            error_message=log_error_msg,
            customer_id=customer_id,
            customer_email=customer_email,
        )
        _fire(
            log_llm_call,
            request_id=request_id,
            session_id=session_id,
            model=model_name,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            response_time_sec=elapsed,
            success=False,
            error_message=log_error_msg,
        )
        _fire(
            log_error,
            request_id=request_id,
            error_type=f"OpenAIError:{type(exc).__name__}",
            message=log_error_msg,
        )
        raise ChatProcessingError("OpenAI request failed") from exc

    if cancelled and cancelled():
        await asyncio.to_thread(db.rollback)
        return

    await asyncio.to_thread(
        _finalize_turn,
        db,
        session_id,
        full_response,
        prompt_tokens,
        completion_tokens,
        total_tokens,
    )

    elapsed = time.perf_counter() - started
    _fire(
        log_chat_turn,
        request_id=request_id,
        session_id=session_id,
        channel=normalized_channel,
        client_ip=client_ip,
        user_message=stored_content,
        ai_response=full_response.strip(),
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        response_time_sec=elapsed,
        has_image=bool(image_url),
        success=True,
        customer_id=customer_id,
        customer_email=customer_email,
    )
    _fire(
        log_llm_call,
        request_id=request_id,
        session_id=session_id,
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        response_time_sec=elapsed,
        success=True,
    )
    metrics_logger.info(
        "chat_turn",
        extra={
            "event": "chat_turn",
            "model": model_name,
            "channel": normalized_channel,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_sec": round(elapsed, 3),
            "success": True,
        },
    )
