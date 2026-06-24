"""Deterministic detection of ticketing intents in a chat message.

In this domain "ticket"/"تذكرة" usually means a *bus* ticket, so the raise
intent keys on complaint / problem / support-request phrasing rather than the
bare word. A reference like GB-2026-000123 is a strong follow-up signal."""

from __future__ import annotations

import re

_REF_RE = re.compile(r"\bGB-\d{4}-\d{4,8}\b", re.IGNORECASE)

# Raise a support ticket / file a complaint.
_RAISE_PATTERNS = [
    # English
    r"\braise (a |an )?(support )?ticket\b",
    r"\bopen (a |an )?(support )?ticket\b",
    r"\bfile (a |an )?(complaint|complain)\b",
    r"\b(make|submit|register|log) (a |an )?(complaint|complain)\b",
    r"\bi (want|need|would like) to complain\b",
    r"\bcomplain about\b",
    r"\breport (a |an )?(problem|issue|complaint|complain)\b",
    r"\b(i have|there is|theres|there's) (a |an )?(problem|issue|complaint|complain)\b",
    r"\bis there (a |any )?way to (make|file|submit|register|log) (a |an )?(complaint|complain)\b",
    r"\bhow (can|do|to) i (make|file|submit|register|log) (a |an )?(complaint|complain)\b",
    r"\bhow (can|do) i complain\b",
    # Arabic
    r"شكوى",
    r"أشتكي|اشتكي|اشكي|أشكي",
    r"تقديم بلاغ|بلاغ",
    r"افتح (لي )?تذكرة|فتح تذكرة",
    r"عايز(ة)? (اقدم|أقدم|اعمل|أعمل) شكوى",
    r"تقديم شكوى|عمل شكوى",
    r"عندي مشكلة|في مشكلة|واجهت مشكلة|مشكلتي",
]

# Follow up on existing ticket(s).
_CHECK_PATTERNS = [
    r"\bmy (support )?ticket(s)?\b",
    r"\bticket status\b",
    r"\bstatus of my\b",
    r"\b(track|follow up on|check) my (ticket|complaint|request)\b",
    r"\bmy complaint(s)?\b",
    r"حالة (الشكوى|التذكرة|الطلب)",
    r"متابعة (شكوى|التذكرة|الطلب|طلبي)",
    r"رقم (الشكوى|التذكرة)",
    r"شكواي|تذكرتي|طلباتي|شكاواي",
]

_RAISE_RE = [re.compile(p, re.IGNORECASE) for p in _RAISE_PATTERNS]
_CHECK_RE = [re.compile(p, re.IGNORECASE) for p in _CHECK_PATTERNS]


def detect_ticket_intent(message: str) -> str | None:
    """Return "check", "raise", or None. Check wins when a ref number is present."""
    text = (message or "").strip()
    if not text:
        return None
    if _REF_RE.search(text):
        return "check"
    if any(r.search(text) for r in _CHECK_RE):
        return "check"
    if any(r.search(text) for r in _RAISE_RE):
        return "raise"
    return None
