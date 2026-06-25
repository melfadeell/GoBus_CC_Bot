"""In-app ticketing agent.

Given the conversation so far, it classifies the support case (category +
priority) and drafts a concise subject + description — "the agent that fetches
the user data from the cc bot and creates the ticket". The result feeds the
deterministic confirmation card the user approves before the ticket is created.

Output is constrained to JSON and validated against the allowed category/priority
sets, with a safe heuristic fallback so chat never breaks on a model hiccup."""

from __future__ import annotations

import json
import logging
import re

from openai import OpenAIError

from app.config import get_settings
from app.core.constants import (
    DEFAULT_TICKET_PRIORITY,
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
)
from app.services.chat_understanding import (
    _is_bus_booking_intent,
    _is_origin_followup,
)
from app.services.openai_client import get_openai_client

logger = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM_PROMPT = f"""You triage GoBus customer-support cases from a chat conversation.

Return ONLY a JSON object with these keys:
- "ready": true ONLY if the customer has actually described their problem (what
  happened / the specifics). false if they only expressed intent to complain or ask
  for help WITHOUT saying what the issue is (e.g. "I want to file a complaint about
  the driver" with no details).
- ready MUST be false when the customer only wants to book a bus trip, find schedules,
  or check prices (e.g. "book a trip to Alexandria", "I'm from Cairo") — that is
  normal travel help, NOT a support ticket. Category "booking" is for booking
  failures/errors, not reserving a route.
- "question": when ready is false, a short friendly question (in the customer's
  language) asking them to describe what happened. Empty string when ready is true.
- "category": one of {list(TICKET_CATEGORIES)}
- "priority": one of {list(TICKET_PRIORITIES)} — set by severity/urgency of the case
- "subject": a short title (<= 80 chars), in the customer's language
- "description": 1-3 sentences summarizing the issue from the customer's point of view, in their language

Priority guidance:
- "urgent": safety, stranded passenger, payment taken with no ticket, today's trip failing
- "high": refund disputes, missed/cancelled trips, lost valuable item
- "medium": general complaints, booking changes, schedule questions turned into an issue
- "low": minor feedback or non-time-sensitive requests

Do not invent facts the customer did not state. Output JSON only, no prose."""


def _fallback_draft(last_user_message: str, *, ready: bool = True) -> dict:
    text = (last_user_message or "").strip()
    subject = (text[:77] + "...") if len(text) > 80 else (text or "Support request")
    return {
        "ready": ready,
        "question": "",
        "category": "other",
        "priority": DEFAULT_TICKET_PRIORITY,
        "subject": subject,
        "description": text or "Customer requested support via chat.",
    }


def _coerce(raw: dict, last_user_message: str) -> dict:
    fb = _fallback_draft(last_user_message)
    category = raw.get("category")
    priority = raw.get("priority")
    subject = (raw.get("subject") or "").strip()
    description = (raw.get("description") or "").strip()
    ready = bool(raw.get("ready", True))
    if ready and (
        _is_bus_booking_intent(last_user_message)
        or _is_origin_followup(last_user_message)
        or re.search(r"\bbook(ing)?\s+(a\s+)?trip\b", (subject + description).lower())
    ):
        ready = False
    return {
        "ready": ready,
        "question": (raw.get("question") or "").strip(),
        "category": category if category in TICKET_CATEGORIES else fb["category"],
        "priority": priority if priority in TICKET_PRIORITIES else fb["priority"],
        "subject": (subject[:200] or fb["subject"]),
        "description": (description or fb["description"]),
    }


async def build_ticket_draft(history: list[dict], last_user_message: str) -> dict:
    """Return {ready, question, category, priority, subject, description}. Never raises."""
    if not settings.openai_api_key:
        return _fallback_draft(last_user_message)

    transcript_lines = [f"{m['role']}: {m['content']}" for m in (history or []) if m.get("content")]
    transcript = "\n".join(transcript_lines[-10:])
    user_content = (
        f"Conversation so far:\n{transcript}\n\n"
        f"Latest customer message:\n{last_user_message}\n\n"
        "Produce the ticket JSON."
    )
    try:
        client = get_openai_client()
        resp = await client.chat.completions.create(
            model=settings.ticketing_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        return _coerce(raw, last_user_message)
    except (OpenAIError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Ticket draft failed (%s); using heuristic fallback", exc)
        return _fallback_draft(last_user_message)
    except Exception as exc:  # pragma: no cover - never break chat
        logger.warning("Ticket draft error (%s); using heuristic fallback", exc)
        return _fallback_draft(last_user_message)
