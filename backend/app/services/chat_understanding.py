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
- "I want to book a trip to Alexandria" / "حجز رحلة" / giving origin ("I'm from Cairo") during booking → trips or faq, wants_live_trips when route/schedules matter, ticket_intent MUST be null — never raise.
- "I need/want to go to <city>" / "I'm going to <city> from <city>" / "عايز اروح <city>" / "3ayz aro7 <city>" → trips, wants_live_trips true (show live trips for that route). ticket_intent null.
- Trip to city X → trips when asking schedule/price, NOT stations (destination is a route endpoint).
- Bare station/area name or "where is X station" → stations.
- "Where do I board?" / "boarding point" / "أركب منين" / "arkab mnen": when a destination/route is named → trips, wants_live_trips true (the backend recommends the nearest boarding station + shows trips from there). With NO destination → stations only. Keep origin + destination in search_query.
- During complaint flow (continue_complaint_flow or ticket_intent raise): do NOT include trips/stations/destinations unless the message is clearly a new unrelated travel question.
- Pure greetings/thanks/ack only (hi, hello, thanks, ok with no travel ask) → faq only, wants_live_trips false, use_history_for_route false — never re-fetch prior trip routes.
- Use conversation context to resolve follow-ups and complaint continuations.
- Output JSON only, no prose."""

# Shorter prompt for the LLM path — same schema, less latency.
_SYSTEM_PROMPT_COMPACT = """Classify a GoBus (Egypt intercity bus) chat turn. Return JSON only:
ticket_intent: null|raise|check; continue_complaint_flow: bool;
content_intents: subset of trips,stations,destinations,services,faq,about,policies;
trip_sort: soonest|latest|cheapest|priciest; trip_limit: 1-12|null;
bus_class: null|standard|elite|business; use_history_for_route: bool;
wants_live_trips: bool (false for how-to-book); wants_service_info: bool;
booking_related: bool; search_query: Arabic-normalized place/route text.
Rules: how-to-book→faq only, no trips; trip prices/schedules→trips; class compare→faq+services;
trip to city→trips not stations; where-do-i-board/arkab mnen/أركب منين with a destination→trips (nearest boarding station shown), without destination→stations;
want-to-book-trip / "need/want to go to X" / "going to X from Y" / origin follow-up→trips wants_live_trips true, ticket_intent null;
complaint flow→no structured cards unless new travel Q; pure hi/hello/thanks→faq only, no history trips."""


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


_ROUTE_CITY_CUES = (
    "cairo", "alexandria", "alex", "hurghada", "dahab", "sharm", "luxor", "port said",
    "nuweiba", "marsa", "makadi", "sokhna", "north coast",
    "القاهرة", "الإسكندرية", "الاسكندرية", "الغردقة", "دهب", "شرم", "الأقصر", "الاقصر",
    "بورسعيد", "نويبع", "مرسى", "مكادى", "السخنة", "الساحل",
)


def _mentions_route(message: str) -> bool:
    text = (message or "").strip()
    lower = text.lower()
    return any(c in lower or c in text for c in _ROUTE_CITY_CUES)


def _is_trip_schedule_query(message: str) -> bool:
    lower = (message or "").lower()
    return bool(
        re.search(
            r"\b(trip|trips|price|prices|schedule|seat|seats|next|cheapest|latest|departure|available)\b"
            r"|سعر|رحلة|رحلات|موعد|مقعد|التالي|أرخص|ارخص|آخر|اخر",
            lower + (message or ""),
        )
    )


def _is_booking_howto(message: str) -> bool:
    lower = (message or "").lower()
    return bool(
        re.search(
            r"how (can i|do i|to) book|how to book|booking steps|ways? to book|can i book"
            r"|كيف (أحجز|احجز|اعمل حجز)|طرق الحجز",
            lower + (message or ""),
        )
    )


def _is_bus_booking_intent(message: str) -> bool:
    """Customer wants to reserve a bus trip — NOT a CRM support ticket."""
    text = (message or "").strip()
    lower = text.lower()
    return bool(
        re.search(
            r"\b(want to|wanna|need to|i'd like to|looking to|help me)\s+book\b"
            r"|book\s+(a\s+)?(trip|bus|ticket|ride|journey)"
            r"|حجز\s+رحلة|أريد\s+أحجز|عايز\s+احجز|ابي\s+احجز|عاوز\s+احجز",
            lower + text,
        )
    )


_TRAVEL_INTENT_RE = re.compile(
    r"\b(?:want|wanna|need|would\s+like|i'?d\s+like|trying|plan(?:ning)?|looking)\s+to\s+"
    r"(?:go|travel|head|get)\b"
    r"|\b(?:go|going|travel|travell?ing|head|heading)\s+to\b"
    r"|عايز\s*(?:ا|أ)?روح|عاوز\s*(?:ا|أ)?روح|نفسي\s*(?:ا|أ)?روح|محتاج\s*(?:ا|أ)?روح|رايح|هروح|اروح"
    r"|3a?yz\s*aroo?7|3a?wz\s*aroo?7|\baroo?7\b|\bro7\b",
    re.IGNORECASE | re.UNICODE,
)


def _is_travel_request(message: str) -> bool:
    """\"I need to go to X\" / \"عايز اروح X\" / \"3ayz aro7 X\" — a travel ask that should
    surface live trips when a route/city is named, even without 'trip/price' keywords."""
    return bool(_TRAVEL_INTENT_RE.search((message or "").strip()))


def _is_origin_followup(message: str) -> bool:
    """Short reply giving departure city after the bot asked where they travel from."""
    text = (message or "").strip()
    lower = text.lower()
    return bool(
        re.search(
            r"^(i'?m\s+from|i\s*am\s+from|iam\s+from|im\s+from|from)\s+\S+"
            r"|^من\s+\S+",
            lower,
        )
    )


def _origin_followup_search_query(message: str, history: list[dict] | None) -> str:
    """Merge origin reply with prior turns so trip SQL resolves the full route."""
    parts = [message.strip()]
    for turn in (history or [])[-6:]:
        content = (turn.get("content") or "").strip()
        if content and content != message.strip():
            parts.append(content)
    return " ".join(parts)[:200]


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


def _assistant_asked_travel_detail(assistant_content: str) -> bool:
    prev = (assistant_content or "").lower()
    return any(p in prev for p in _ASSISTANT_TRAVEL_PROMPTS)


def _is_service_compare(message: str) -> bool:
    lower = (message or "").lower()
    if not re.search(r"difference|compare|vs\.?|فرق|الفرق", lower + (message or "")):
        return False
    return bool(
        _extract_bus_class(message)
        or re.search(r"\b(standard|elite|business|gomini|golemo|جوميني|جوليمو)\b", lower)
    )


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

_COMPLAINT_DETAIL_PROMPTS = (
    "describe what happened",
    "what happened",
    "describe the problem",
    "وصف المشكلة",
    "ما الذي حدث",
)


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


def _smalltalk_understanding(message: str) -> ChatUnderstanding:
    return ChatUnderstanding(
        content_intents={"faq"},
        search_query=(message or "").strip(),
        wants_live_trips=False,
        use_history_for_route=False,
    )


def _is_station_query(message: str) -> bool:
    lower = (message or "").lower()
    return bool(
        re.search(
            r"\b(station|stations|nearest|closest|where is|map|address|location|working hours|opening hours)\b"
            r"|محطة|فين|أقرب|اقرب|موقع|خريطة|مواعيد",
            lower + (message or ""),
        )
    )


_BOARDING_RE = re.compile(
    r"where\s+(?:do|can|should|to)\s+(?:i\s+)?board"
    r"|boarding\s+(?:point|station|place|location|spot)"
    r"|pick[\s-]?up\s+(?:point|location|station)"
    r"|\barkab\s+(?:mn|men|mnen|mnein|mneen|min|from)"
    r"|أركب\s*م?نين|اركب\s*م?نين|أركب\s*من\s*فين|اركب\s*من\s*فين"
    r"|أركب\s*فين|اركب\s*فين|نقطة\s*(?:الركوب|الانطلاق|الإنطلاق)|محطة\s*الركوب",
    re.IGNORECASE | re.UNICODE,
)


def _is_boarding_question(message: str) -> bool:
    """\"Where do I board?\" / \"arkab mnen\" — the customer wants the boarding STATION,
    not a trips table. Mentioning a destination must not reroute this to trips."""
    return bool(_BOARDING_RE.search((message or "").strip()))


def _clear_ticket_if_travel_booking(u: ChatUnderstanding, message: str) -> None:
    """Bus trip booking must never open the CRM complaint form."""
    if u.ticket_intent == "raise" or u.continue_complaint_flow:
        if u.wants_live_trips or _is_bus_booking_intent(message) or _is_origin_followup(message):
            u.ticket_intent = None
            u.continue_complaint_flow = False


def _apply_intent_coercion(u: ChatUnderstanding, message: str = "") -> None:
    """Shared post-processing for fast + LLM paths."""
    if u.wants_service_info:
        u.content_intents.add("faq")
        u.content_intents.add("services")
        u.content_intents.discard("trips")
    if u.booking_related and not u.wants_live_trips:
        u.content_intents.discard("trips")
    if not u.wants_live_trips:
        u.content_intents.discard("trips")
    _clear_ticket_if_travel_booking(u, message)


def fast_understanding(message: str, *, history: list[dict] | None = None) -> tuple[ChatUnderstanding, bool]:
    """Local routing for common turns. Returns (understanding, confident).

    When confident=True the understanding LLM can be skipped (~1–3s saved).
    """
    msg = (message or "").strip()
    if not msg:
        return _fallback(msg), False

    u = ChatUnderstanding(search_query=msg)
    u.bus_class = _extract_bus_class(msg)
    lower = msg.lower()

    if re.search(r"\bGB-\d{4}-\d{4,8}\b", msg, re.IGNORECASE):
        u.ticket_intent = "check"
        u.content_intents = {"faq"}
        u.wants_live_trips = False
        return u, True

    # Complaint continuation takes priority: when the assistant just asked the
    # customer to describe their problem, THIS turn is the answer — even if it
    # mentions "book a ticket" (past-tense complaint about an existing booking).
    # Must run before the booking/trip heuristics so a complaint reply like
    # "I did book a ticket but it isn't shown" never triggers a trips table.
    if _assistant_awaiting_complaint_detail(history):
        u.continue_complaint_flow = True
        u.ticket_intent = "raise"
        u.wants_live_trips = False
        u.content_intents = {"faq"}
        return u, True

    if _is_booking_howto(msg):
        u.booking_related = True
        u.wants_live_trips = False
        u.content_intents = {"faq"}
        return u, True

    if _is_bus_booking_intent(msg):
        u.booking_related = True
        u.wants_live_trips = True
        u.content_intents = {"trips"}
        u.ticket_intent = None
        return u, True

    if _is_origin_followup(msg) and history:
        u.wants_live_trips = True
        u.content_intents = {"trips"}
        u.use_history_for_route = True
        u.ticket_intent = None
        u.search_query = _origin_followup_search_query(msg, history)
        return u, True

    if _is_service_compare(msg):
        u.wants_service_info = True
        u.wants_live_trips = False
        u.content_intents = {"faq", "services"}
        return u, True

    if re.search(
        r"\b(file a complaint|raise (a )?ticket|complain about|my complaint)\b|شكوى|عندي مشكلة",
        lower + msg,
    ):
        u.ticket_intent = "raise"
        u.wants_live_trips = False
        u.content_intents = {"faq"}
        return u, True

    if re.search(r"\bmy (support )?ticket|ticket status|my complaint\b|تذكرتي|حالة الشكوى", lower + msg):
        u.ticket_intent = "check"
        u.wants_live_trips = False
        u.content_intents = {"faq"}
        return u, True

    # "Where do I board?" / "arkab mnen". When a destination/route is named, the
    # customer wants the boarding point AND the trips from there — the trips path
    # recommends the nearest GoBus origin station when their city isn't served.
    # A bare boarding question (no route) just resolves the boarding station.
    if _is_boarding_question(msg):
        if _mentions_route(msg):
            u.wants_live_trips = True
            u.content_intents = {"trips"}
        else:
            u.wants_live_trips = False
            u.content_intents = {"stations"}
        return u, True

    if _is_station_query(msg) and not _is_trip_schedule_query(msg):
        u.wants_live_trips = False
        u.content_intents = {"stations"}
        return u, True

    if (_is_trip_schedule_query(msg) or _is_travel_request(msg)) and (
        _mentions_route(msg) or u.bus_class
    ):
        u.wants_live_trips = True
        u.content_intents = {"trips"}
        if re.search(r"cheapest|أرخص|ارخص|lowest", lower + msg):
            u.trip_sort = "cheapest"
        elif re.search(r"latest|last|آخر|اخر|أحدث", lower + msg):
            u.trip_sort = "latest"
        elif re.search(r"priciest|most expensive|أغلى|اغلى", lower + msg):
            u.trip_sort = "priciest"
        m = re.search(r"\b(\d{1,2})\s*(?:trips?|رحلات?)\b", lower)
        if m:
            u.trip_limit = int(m.group(1))
        if re.fullmatch(r"\s*\d{1,2}\s*", msg):
            u.trip_limit = int(msg.strip())
            u.use_history_for_route = True
        if re.search(r"latest|last|cheapest|more|another|كمان|تاني|المزيد", lower + msg) and not _mentions_route(
            msg
        ):
            u.use_history_for_route = True
        return u, True

    if is_smalltalk(msg, history=history):
        return _smalltalk_understanding(msg), True

    _apply_intent_coercion(u, msg)
    return u, False


def understanding_affects_retrieval(a: ChatUnderstanding, b: ChatUnderstanding) -> bool:
    """True when two understandings would fetch different data."""
    return (
        a.content_intents != b.content_intents
        or a.wants_live_trips != b.wants_live_trips
        or a.in_complaint_flow != b.in_complaint_flow
        or a.bus_class != b.bus_class
        or a.use_history_for_route != b.use_history_for_route
        or a.booking_related != b.booking_related
        or a.wants_service_info != b.wants_service_info
        or a.trip_sort != b.trip_sort
        or a.trip_limit != b.trip_limit
        or (a.search_query or "").strip() != (b.search_query or "").strip()
    )


def _fallback(message: str) -> ChatUnderstanding:
    text = (message or "").strip()
    return ChatUnderstanding(
        content_intents={"faq"},
        search_query=text,
    )


def _coerce(raw: dict, message: str, *, history: list[dict] | None = None) -> ChatUnderstanding:
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

    # Bus-booking intent normally cancels a complaint flow — but NOT when the
    # assistant just asked for complaint details: a reply like "I did book a
    # ticket but it isn't shown" is a complaint answer, not a booking request.
    if (ticket == "raise" or bool(raw.get("continue_complaint_flow"))) and not (
        _assistant_awaiting_complaint_detail(history)
    ):
        if wants_live_trips or _is_bus_booking_intent(message) or _is_origin_followup(message):
            ticket = None
            raw["continue_complaint_flow"] = False

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

    u = ChatUnderstanding(
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
    if is_smalltalk(message, history=history):
        u.wants_live_trips = False
        u.use_history_for_route = False
        u.content_intents = {"faq"}
        u.ticket_intent = None
        u.continue_complaint_flow = False
    return u


async def understand_message(
    message: str,
    *,
    history: list[dict] | None = None,
) -> ChatUnderstanding:
    """Classify the user turn from message + short conversation history. Never raises."""
    msg = (message or "").strip()
    if not msg:
        return _fallback(msg)
    if is_smalltalk(msg, history=history):
        return _smalltalk_understanding(msg)
    if not settings.openai_api_key or not settings.chat_understanding_enabled:
        return _fallback(msg)

    transcript_lines: list[str] = []
    max_turns = max(2, settings.chat_understanding_history_turns)
    for turn in (history or [])[-max_turns:]:
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
                {"role": "system", "content": _SYSTEM_PROMPT_COMPACT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        return _coerce(raw, msg, history=history)
    except (OpenAIError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Chat understanding failed (%s); using safe fallback", exc)
        return _fallback(msg)
    except Exception as exc:  # pragma: no cover - never break chat
        logger.warning("Chat understanding error (%s); using safe fallback", exc)
        return _fallback(msg)
