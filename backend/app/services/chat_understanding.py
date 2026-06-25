"""LLM-based chat understanding — decides routing from message + context.

Replaces keyword/regex intent detection. One fast model call per turn returns
what data to fetch (trips, stations, KB, tickets) and how (sort, limit, route
from history), plus a normalized search query for the database layer."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from openai import OpenAIError

from app.config import get_settings
from app.services.openai_client import get_openai_client

logger = logging.getLogger(__name__)
settings = get_settings()

VALID_CONTENT_INTENTS = frozenset(
    {"trips", "stations", "destinations", "services", "faq", "about", "policies"}
)
VALID_TRIP_SORT = frozenset({"soonest", "latest", "cheapest", "priciest"})
VALID_TICKET_INTENTS = frozenset({"raise", "check"})
VALID_BUS_CLASSES = frozenset({"standard", "elite", "business"})

_SYSTEM_PROMPT = """You analyze a GoBus customer-support chat turn and decide what the backend should fetch.

GoBus is an Egyptian intercity bus company. Customers ask about schedules, prices, stations, destinations, booking, policies, and sometimes file support complaints (NOT bus tickets).

Return ONLY a JSON object with these keys:
- "ticket_intent": null | "raise" | "check"
  - "raise": file a complaint / report a problem / customer-support ticket (شكوى، مشكلة، report issue). NOT buying a bus ticket.
  - "check": follow up on an existing support ticket / complaint status (my ticket, GB-2026-..., حالة الشكوى).
  - null: normal travel/info question.
- "continue_complaint_flow": boolean — true ONLY when the assistant previously asked the customer to describe their complaint/problem and this message is their answer (even without complaint keywords).
- "content_intents": array — subset of: trips, stations, destinations, services, faq, about, policies. Pick all that apply; at least one.
  - trips: schedules, prices, seats, next/last/cheapest trip, route availability
  - stations: station location, address, map, nearest station, working hours
  - destinations: city guides, what to visit, about a destination city
  - services: bus classes (Standard/Elite/Business), GoMini, GoLemo, comparisons
  - faq: how to book, app, hotline, general how-to
  - about: company info, ownership, history, vision
  - policies: refund, cancellation, terms, privacy
- "trip_sort": "soonest" | "latest" | "cheapest" | "priciest" — only when trips intent applies; default soonest
- "trip_limit": integer 1-12 or null — explicit count when customer asks for N trips
- "bus_class": null | "standard" | "elite" | "business" — set when the customer asks for ONE specific class only (e.g. "elite trips", "standard class prices"). null when any class is fine.
- "use_history_for_route": boolean — true when the message is a follow-up that omits origin/destination but refers to a prior route (e.g. "the latest 5", "show 3 more", "cheapest one")
- "wants_live_trips": boolean — true ONLY when the customer wants actual trip rows (schedule, price, seats, next departure) for a route. false for "how to book", booking steps, app help, or policy questions even if they say "ticket".
- "wants_service_info": boolean — true for bus-class comparisons (standard/elite/business), service differences, GoMini/GoLemo questions.
- "booking_related": boolean — true when the question is about the booking process (how/where to book), not live schedules.
- "search_query": one-line normalized search text for the Arabic trips/stations DB — translate EN/Franco place names to Arabic, fix typos, split glued prepositions; preserve route/sort/count intent; do NOT answer the question

Rules:
- "How to book" / booking steps / "can I book online" → faq ONLY, booking_related true, wants_live_trips false. Do NOT include trips.
- "Trip prices Cairo to Hurghada" / "next bus to Alexandria" → trips, wants_live_trips true.
- "Difference between standard and elite" / bus classes → faq + services, wants_service_info true, wants_live_trips false. Do NOT include trips.
- Bus ticket / "تذكرة حجز" for HOW to book → faq, NOT ticket_intent raise.
- Trip to city X → trips when asking schedule/price, NOT stations (destination is a route endpoint).
- Bare station/area name or "where is X station" → stations.
- During complaint flow (continue_complaint_flow or ticket_intent raise): do NOT include trips/stations/destinations unless the message is clearly a new unrelated travel question.
- Use conversation context to resolve follow-ups and complaint continuations.
- Output JSON only, no prose."""


@dataclass
class ChatUnderstanding:
    ticket_intent: str | None = None
    continue_complaint_flow: bool = False
    content_intents: set[str] = field(default_factory=lambda: {"faq"})
    trip_sort: str = "soonest"
    trip_limit: int | None = None
    use_history_for_route: bool = False
    wants_live_trips: bool = False
    wants_service_info: bool = False
    booking_related: bool = False
    bus_class: str | None = None
    search_query: str = ""

    @property
    def in_complaint_flow(self) -> bool:
        return self.ticket_intent == "raise" or self.continue_complaint_flow


def _extract_bus_class(message: str) -> str | None:
    """Detect a requested bus class from the user message (fallback for the LLM)."""
    text = (message or "").strip()
    if not text:
        return None
    lower = text.lower()
    for cls in VALID_BUS_CLASSES:
        if re.search(rf"\b{re.escape(cls)}\b", lower):
            return cls
    if re.search(r"\bايليت\b|\bإيليت\b", text, re.IGNORECASE):
        return "elite"
    if re.search(r"\bستاندرد\b|\bستاندراد\b", text, re.IGNORECASE):
        return "standard"
    if re.search(r"\bبيزنس\b|\bبزنس\b", text, re.IGNORECASE):
        return "business"
    return None


def _fallback(message: str) -> ChatUnderstanding:
    text = (message or "").strip()
    return ChatUnderstanding(
        content_intents={"faq"},
        search_query=text,
    )


def _coerce(raw: dict, message: str) -> ChatUnderstanding:
    fb = _fallback(message)
    ticket = raw.get("ticket_intent")
    if ticket not in VALID_TICKET_INTENTS:
        ticket = None

    intents_raw = raw.get("content_intents")
    intents: set[str] = set()
    if isinstance(intents_raw, list):
        intents = {i for i in intents_raw if isinstance(i, str) and i in VALID_CONTENT_INTENTS}
    if not intents:
        intents = set(fb.content_intents)

    wants_live_trips = bool(raw.get("wants_live_trips"))
    wants_service_info = bool(raw.get("wants_service_info"))
    booking_related = bool(raw.get("booking_related"))

    if wants_service_info:
        intents.add("faq")
        intents.add("services")
        intents.discard("trips")
    if booking_related and not wants_live_trips:
        intents.discard("trips")
    if not wants_live_trips:
        intents.discard("trips")

    trip_sort = raw.get("trip_sort") or "soonest"
    if trip_sort not in VALID_TRIP_SORT:
        trip_sort = "soonest"

    trip_limit = raw.get("trip_limit")
    if trip_limit is not None:
        try:
            trip_limit = int(trip_limit)
            if not (1 <= trip_limit <= 12):
                trip_limit = None
        except (TypeError, ValueError):
            trip_limit = None

    search_query = (raw.get("search_query") or message or "").strip()
    if not search_query:
        search_query = fb.search_query

    bus_class = raw.get("bus_class")
    if bus_class not in VALID_BUS_CLASSES:
        bus_class = _extract_bus_class(message)

    return ChatUnderstanding(
        ticket_intent=ticket,
        continue_complaint_flow=bool(raw.get("continue_complaint_flow")),
        content_intents=intents,
        trip_sort=trip_sort,
        trip_limit=trip_limit,
        use_history_for_route=bool(raw.get("use_history_for_route")),
        wants_live_trips=wants_live_trips,
        wants_service_info=wants_service_info,
        booking_related=booking_related,
        bus_class=bus_class,
        search_query=search_query[:200],
    )


async def understand_message(
    message: str,
    *,
    history: list[dict] | None = None,
) -> ChatUnderstanding:
    """Classify the user turn from message + short conversation history. Never raises."""
    msg = (message or "").strip()
    if not msg:
        return _fallback(msg)
    if not settings.openai_api_key or not settings.chat_understanding_enabled:
        return _fallback(msg)

    transcript_lines: list[str] = []
    for turn in (history or [])[-10:]:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if content:
            transcript_lines.append(f"{role}: {content}")
    transcript = "\n".join(transcript_lines)

    user_content = msg
    if transcript:
        user_content = f"Conversation so far:\n{transcript}\n\nLatest customer message:\n{msg}"

    try:
        client = get_openai_client()
        resp = await client.chat.completions.create(
            model=settings.chat_understanding_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=250,
            response_format={"type": "json_object"},
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        return _coerce(raw, msg)
    except (OpenAIError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Chat understanding failed (%s); using safe fallback", exc)
        return _fallback(msg)
    except Exception as exc:  # pragma: no cover - never break chat
        logger.warning("Chat understanding error (%s); using safe fallback", exc)
        return _fallback(msg)
