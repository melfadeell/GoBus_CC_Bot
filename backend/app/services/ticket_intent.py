"""Deprecated: ticket intent is classified by ``chat_understanding.understand_message``.

This module is kept only so older imports don't break. Do not add keyword logic here."""

from app.services.chat_understanding import understand_message


async def detect_ticket_intent_async(message: str, *, history: list[dict] | None = None) -> str | None:
    """LLM-based ticket intent (raise / check / None)."""
    return (await understand_message(message, history=history)).ticket_intent
