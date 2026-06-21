from collections.abc import AsyncGenerator, Callable
import time

from openai import AsyncOpenAI, OpenAIError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import (
    CHAT_CHANNELS,
    DEFAULT_CHAT_CHANNEL,
    DEFAULT_GREETING_AR,
    DEFAULT_HOTLINE,
    DEFAULT_SYSTEM_PROMPT,
)
from app.core.guardrails import HARD_GUARDRAILS
from app.models.models import BotSettings, ChatMessage, ChatSession
from app.services.kb_retrieval import retrieve_context
from app.services.logs_writer import log_chat_turn, log_llm_call

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


def _build_system_prompt(bot_settings: BotSettings, context: str) -> str:
    formatting = """
--- Response format (mandatory) ---
Use Markdown: ## headers for sections, - bullets for lists. No wall-of-text paragraphs.
Separate each service/topic under its own header. Short paragraphs only.
When KB includes a station Map URL, always show it as a clickable Markdown link.
"""
    kb_context = (
        context
        if context
        else "No GoBus-specific KB matches for this query. General questions may still be answered helpfully."
    )
    return f"""{HARD_GUARDRAILS}

{bot_settings.system_prompt}
{formatting}

--- سياق قاعدة المعرفة (GoBus) ---
{kb_context}
"""


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
) -> AsyncGenerator[str, None]:
    if not settings.openai_api_key:
        raise ChatProcessingError("OpenAI API key is not configured")

    started = time.perf_counter()
    normalized_channel = normalize_channel(channel)
    get_or_create_session(db, session_id, normalized_channel)

    stored_content = _build_user_content(user_message, ocr_text)
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=stored_content,
        image_url=image_url,
    )
    db.add(user_msg)
    db.flush()

    bot_settings = get_bot_settings(db)
    context = retrieve_context(db, user_message or (ocr_text or ""))
    history = get_conversation_history(db, session_id)
    model_name = bot_settings.model_name or settings.openai_model

    messages = [{"role": "system", "content": _build_system_prompt(bot_settings, context)}]
    messages.extend(history)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    full_response = ""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    log_error_msg: str | None = None

    try:
        stream = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            temperature=0.3,
        )

        async for chunk in stream:
            if cancelled and cancelled():
                db.rollback()
                return

            if getattr(chunk, "usage", None):
                prompt_tokens = chunk.usage.prompt_tokens or 0
                completion_tokens = chunk.usage.completion_tokens or 0
                total_tokens = chunk.usage.total_tokens or 0

            if not chunk.choices:
                continue
            delta = getattr(chunk.choices[0].delta, "content", None)
            if delta:
                full_response += delta
                yield delta

    except OpenAIError as exc:
        db.rollback()
        log_error_msg = str(exc)
        elapsed = time.perf_counter() - started
        log_chat_turn(
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
        )
        log_llm_call(
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
        raise ChatProcessingError("OpenAI request failed") from exc

    if cancelled and cancelled():
        db.rollback()
        return

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

    elapsed = time.perf_counter() - started
    log_chat_turn(
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
    )
    log_llm_call(
        request_id=request_id,
        session_id=session_id,
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        response_time_sec=elapsed,
        success=True,
    )
