import asyncio
from collections.abc import AsyncGenerator, Callable
import json
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
from app.models.models import BotSettings, ChatMessage, ChatSession
from app.services.chat_understanding import is_smalltalk
from app.services.chat_tools import TOOLS, run_tool
from app.services.kb_retrieval import _HISTORY_SEP
from app.services.logs_writer import log_chat_turn, log_error, log_llm_call

settings = get_settings()

_bot_settings_cache: tuple[float, dict] | None = None


def _cached_bot_config(db: Session) -> dict:
    """In-process TTL cache for bot prompt/model/hotline (read every chat turn)."""
    global _bot_settings_cache
    now = time.monotonic()
    if _bot_settings_cache and _bot_settings_cache[0] > now:
        return _bot_settings_cache[1]
    bot = get_bot_settings(db)
    data = {
        "system_prompt": bot.system_prompt,
        "model_name": bot.model_name or settings.openai_model,
        "hotline": bot.hotline or DEFAULT_HOTLINE,
    }
    _bot_settings_cache = (now + settings.bot_settings_cache_ttl, data)
    return data


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


def _is_dangling_reply(text: str) -> bool:
    """True when the reply ends mid-sentence on a colon — the classic incomplete
    "the nearest station is:" with nothing after it."""
    stripped = (text or "").rstrip()
    return bool(stripped) and stripped[-1] in {":", "："}


def _dangling_completion(message: str, hotline: str) -> str:
    """A complete, language-matched fallback appended when a reply would otherwise
    be left dangling on a colon with no card/table to follow it."""
    if re.search(r"[؀-ۿ]", message or ""):
        return (
            "للأسف لا تتوفر لديّ تفاصيل كافية للرد على هذا الطلب الآن. "
            f"يرجى توضيح المدينة أو المحطة المطلوبة، أو التواصل مع الخط الساخن {hotline}."
        )
    return (
        "Sorry, I don't have enough details to fully answer that right now. "
        f"Please clarify the city or station you mean, or contact our hotline {hotline}."
    )


def _structured_fallback_text(message: str) -> str:
    """One-line intro when structured cards/tables were already shown but the final
    LLM answer call failed."""
    if re.search(r"[؀-ۿ]", message or ""):
        return "النتائج متاحة أدناه."
    return "The results are shown below."


def _build_system_prompt(system_prompt: str, hotline: str, message: str = "") -> str:
    formatting = """
--- Response format (mandatory) ---
Use Markdown: ## headers for sections, - bullets for lists. No wall-of-text paragraphs.
Short paragraphs only.
"""
    tool_rules = """
--- Tools (mandatory) ---
You cannot see the GoBus database directly. To answer ANYTHING about trips, schedules,
prices, seats, stations, addresses, destinations served, bus classes/services, booking,
policies, or support tickets, you MUST call the matching tool and use its result. NEVER
invent or guess trips, prices, schedules, seat counts, addresses, or ticket details, and
never tell the customer to check the app/website for data a tool can provide.
When you call a tool, do NOT write any text in that same turn — reply only after the tool
result returns. After a tool says it has shown the user a table/card/chips (trips, station,
destinations list, ticket form, or ticket list), reply with ONE short intro line and do NOT
repeat or re-list that data yourself. If a tool reports no match, say so plainly and offer
the hotline {{HOTLINE}} or the GoBus app.
"""
    voice_rules = """
--- Internal terms (mandatory) ---
NEVER reveal or mention your internal systems or data sources to the customer. Do NOT use
words like "KB", "knowledge base", "database", "context", "tool", "section", "block", or
"records" in your reply. When information is unavailable, say it naturally as GoBus —
e.g. "I don't have more details on that right now" — never "the KB doesn't list it" or
"that's not in my context".
"""
    assembled = f"""{HARD_GUARDRAILS}

{system_prompt}
{formatting}{tool_rules}{voice_rules}{_reply_language_directive(message)}"""
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
    bot_cfg = _cached_bot_config(db)
    history = get_conversation_history(db, session_id)
    return {
        "system_prompt": bot_cfg["system_prompt"],
        "model_name": bot_cfg["model_name"],
        "history": history,
        "hotline": bot_cfg["hotline"],
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


def _create_kwargs(model_name: str, messages: list[dict], **extra) -> dict:
    """Shared OpenAI request kwargs with the temperature guard for reasoning models."""
    kwargs: dict = {"model": model_name, "messages": messages, **extra}
    # GPT-5 / reasoning models only accept the default temperature; sending a custom
    # value returns a 400. Other models keep the tuned low temperature.
    if not model_name.lower().startswith(("gpt-5", "o1", "o3", "o4")):
        kwargs["temperature"] = 0.3
    return kwargs


_STRUCTURED_META_KEYS = ("trips", "stations", "destinations", "draft", "tickets_crm")


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

    messages: list[dict] = [
        {"role": "system", "content": _build_system_prompt(system_prompt, hotline, raw_query)}
    ]
    messages.extend(history)

    client = get_openai_client()
    full_response = ""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    ttft_sent = False
    structured_shown = False
    # Greetings/thanks/acks never need data — skip tool calling for a faster reply.
    allow_tools_turn = not is_smalltalk(raw_query, history=history)

    def _accumulate_usage(usage) -> None:
        nonlocal prompt_tokens, completion_tokens, total_tokens
        if usage:
            prompt_tokens += usage.prompt_tokens or 0
            completion_tokens += usage.completion_tokens or 0
            total_tokens += usage.total_tokens or 0

    try:
        max_rounds = max(1, settings.chat_tool_max_rounds)
        for round_idx in range(max_rounds + 1):
            if cancelled and cancelled():
                await asyncio.to_thread(db.rollback)
                return

            # The final allowed round forbids tools so the model must produce text.
            offer_tools = allow_tools_turn and round_idx < max_rounds
            kwargs = _create_kwargs(
                model_name,
                messages,
                stream=True,
                stream_options={"include_usage": True},
            )
            if offer_tools:
                kwargs["tools"] = TOOLS
                kwargs["tool_choice"] = "auto"

            stream = await client.chat.completions.create(**kwargs)

            tool_calls: dict[int, dict] = {}
            content_buf = ""
            async for chunk in stream:
                if cancelled and cancelled():
                    await asyncio.to_thread(db.rollback)
                    return
                _accumulate_usage(getattr(chunk, "usage", None))
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                for tc in getattr(delta, "tool_calls", None) or []:
                    slot = tool_calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn and fn.name:
                        slot["name"] = fn.name
                    if fn and fn.arguments:
                        slot["args"] += fn.arguments
                token = getattr(delta, "content", None)
                if token:
                    if not ttft_sent:
                        ttft_sent = True
                        yield {
                            "type": "meta",
                            "ttft_ms": int((time.perf_counter() - started) * 1000),
                        }
                    full_response += token
                    yield {"type": "token", "content": token}

            if not tool_calls:
                # No tools requested — the streamed content is the final answer.
                break

            # Execute the requested tools, surface their cards/tables, and loop so the
            # model can write its reply grounded in the results.
            ordered = [tool_calls[i] for i in sorted(tool_calls)]
            messages.append(
                {
                    "role": "assistant",
                    "content": content_buf or None,
                    "tool_calls": [
                        {
                            "id": t["id"] or f"call_{i}",
                            "type": "function",
                            "function": {"name": t["name"], "arguments": t["args"] or "{}"},
                        }
                        for i, t in enumerate(ordered)
                    ],
                }
            )
            for i, t in enumerate(ordered):
                try:
                    args = json.loads(t["args"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result_text, metas = await run_tool(
                    t["name"],
                    args,
                    db=db,
                    message=raw_query,
                    history=history,
                    history_text=history_text,
                    customer_id=customer_id,
                    channel=normalized_channel,
                )
                for meta in metas:
                    if any(k in meta for k in _STRUCTURED_META_KEYS):
                        structured_shown = True
                    yield meta
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": t["id"] or f"call_{i}",
                        "content": (result_text or "").replace("{{HOTLINE}}", hotline),
                    }
                )

    except OpenAIError as exc:
        if structured_shown:
            # Cards/tables already reached the user — give a complete one-line intro
            # instead of failing the whole turn.
            fallback_text = _structured_fallback_text(raw_query)
            full_response = fallback_text
            yield {"type": "token", "content": fallback_text}
            await asyncio.to_thread(_finalize_turn, db, session_id, full_response, 0, 0, 0)
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
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                response_time_sec=elapsed,
                has_image=bool(image_url),
                success=True,
                error_message=f"LLM unavailable; structured fallback used: {exc}",
                customer_id=customer_id,
                customer_email=customer_email,
            )
            return

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

    # Safety net: never leave the customer with an incomplete "...is:" reply when
    # there's no card/table to follow it.
    if not structured_shown and _is_dangling_reply(full_response):
        completion = " " + _dangling_completion(raw_query, hotline)
        full_response += completion
        yield {"type": "token", "content": completion}

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
