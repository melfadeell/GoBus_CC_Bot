"""Smalltalk detection for the chat agent.

Routing (what data to fetch, ticket handling, etc.) is now decided by the LLM via
tool calling — see ``chat_tools``. The only local shortcut kept here is detecting
pure greetings/thanks/acks so those turns can skip the tool-calling round entirely.
"""

from __future__ import annotations

import re

_SMALLTALK_RE = re.compile(
    r"^(?:"
    r"hi(?:\s+there|\s+again)?|"
    r"hello(?:\s+there|\s+again)?|"
    r"hey(?:\s+there)?|"
    r"hiya|howdy|yo|sup|"
    r"good\s+(?:morning|afternoon|evening|night)|"
    r"thanks?(?:\s+you)?|thank\s+you|thx|ty|"
    r"ok(?:ay)?|k|cool|great|nice|perfect|awesome|"
    r"bye|goodbye|see\s+ya|"
    r"مرحبا?|أ?هلا+|السلام\s+عليكم|"
    r"شكرا?|متشكر|"
    r"تمام|اوك|طيب"
    r")[\s!.?,]*$",
    re.IGNORECASE | re.UNICODE,
)

_ASSISTANT_TRAVEL_PROMPTS = (
    "departure",
    "depart from",
    "where are you traveling from",
    "where are you travelling from",
    "specify your departure",
    "traveling from",
    "travelling from",
    "book a trip",
    "booking a trip",
    "منين",
    "من أين",
    "من اين",
    "نقطة الانطلاق",
    "نقطة انطلاق",
)

_COMPLAINT_DETAIL_PROMPTS = (
    "describe what happened",
    "what happened",
    "describe the problem",
    "وصف المشكلة",
    "ما الذي حدث",
)


def _assistant_asked_travel_detail(assistant_content: str) -> bool:
    prev = (assistant_content or "").lower()
    return any(p in prev for p in _ASSISTANT_TRAVEL_PROMPTS)


def _assistant_awaiting_complaint_detail(history: list[dict] | None) -> bool:
    """True when the bot just asked the customer to describe their complaint."""
    if not history:
        return False
    for turn in reversed(history[-4:]):
        if turn.get("role") != "assistant":
            continue
        prev = turn.get("content") or ""
        if _assistant_asked_travel_detail(prev):
            return False
        prev_lower = prev.lower()
        return any(p in prev_lower for p in _COMPLAINT_DETAIL_PROMPTS)
    return False


def is_smalltalk(message: str, *, history: list[dict] | None = None) -> bool:
    """True when the turn is only a greeting/thanks/ack — no travel or ticket intent."""
    msg = (message or "").strip()
    if not msg or len(msg) > 80:
        return False
    if _assistant_awaiting_complaint_detail(history):
        return False
    return bool(_SMALLTALK_RE.match(msg))
