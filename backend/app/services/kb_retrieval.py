"""Knowledge base retrieval helpers for chat context."""

import re
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.constants import CITY_STATION_NAMES
from app.models.models import Destination, KbArticle, KbCategory, Route, Service, Station, Trip
from app.services.reference_cache import (
    active_destinations,
    active_routes,
    active_services,
    active_stations,
)
from app.utils.text_utils import normalize_arabic

TRIP_KEYWORDS = {
    "رحلة", "موعد", "مقعد", "trip", "seat", "schedule", "next", "available", "مواعيد", "التالي", "رحلات",
    "price", "prices", "سعر", "أسعار", "departure", "arrival", "مغادرة", "وصول",
}
BOOKING_KEYWORDS = {"book", "booking", "حجز", "احجز", "أحجز", "تذكرة", "ticket", "reserve"}
FAQ_KEYWORDS = {
    "faq", "how do", "how can", "how to", "what is", "what are", "why", "when", "where can i",
    "hotline", "phone", "contact", "call",
    "كيف", "ما هو", "ما هي", "لماذا", "متى", "هل يمكن", "أسئلة", "سؤال", "الخط الساخن", "اتصل",
}
POLICY_KEYWORDS = {
    "policy", "policies", "terms", "conditions", "cancel", "cancellation", "refund", "privacy",
    "سياسة", "سياسات", "شروط", "أحكام", "إلغاء", "استرداد", "خصوصية", "استرجاع",
}
DESTINATION_KEYWORDS = {
    "destination", "destinations", "guide", "visit", "about dahab", "about alex",
    "وجهة", "وجهات", "دليل", "زيارة", "عن مدينة", "tell me about",
}
SERVICE_KEYWORDS = {
    "gomini", "golemo", "جوميني", "جوليمو", "go mini", "go lemo",
    "difference between", " vs ", "compare", "الفرق بين", "مقارنة",
}
GENERAL_COMPANY_KEYWORDS = {
    "owner",
    "ownership",
    "who owns",
    "who is",
    "about gobus",
    "about us",
    "company",
    "history",
    "founded",
    "establish",
    "vision",
    "mission",
    "shareholder",
    "corporate",
    "general inquiry",
    "general information",
    "مالك",
    "ملكية",
    "من يملك",
    "شركة",
    "عن جوباص",
    "عن الشركة",
    "معلومات عنا",
    "معلومات عامة",
    "تاريخ",
    "تأسست",
    "رؤية",
    "مهمة",
    "مساهمة",
}

STATION_KEYWORDS = {
    "station", "stations", "location", "map", "where", "address", "directions", "branch", "office",
    "nearest", "closest", "near", "street",
    "محطة", "محطه", "موقع", "فين", "عنوان", "خريطة", "مكان", "فرع", "لوكيشن",
    "أقرب", "اقرب", "قريب", "قريبة", "شارع", "ميدان", "منطقة",
}

STATION_ALIASES: dict[str, list[str]] = {
    "giza": ["الجيزة", "جيزة"],
    "madinaty": ["مدينتي"],
    "madinty": ["مدينتي"],
    "heliopolis": ["مصر الجديدة", "الماظة", "الألماظة"],
    "nasr city": ["مدينة نصر"],
    "maadi": ["المعادي"],
    "october": ["أكتوبر", "السادس من أكتوبر", "6 اكتوبر"],
    "alexandria": ["الإسكندرية", "الاسكندرية"],
    "hurghada": ["الغردقة"],
    "sharm": ["شرم الشيخ"],
    "dahab": ["دهب"],
    "port said": ["بورسعيد", "بور سعيد"],
    "sokhna": ["العين السخنة", "السخنة"],
}

# English query terms → Arabic destination/route fragments
DESTINATION_ALIASES: dict[str, list[str]] = {
    "dahab": ["دهب", "مدينة دهب"],
    "alexandria": ["الإسكندرية", "الاسكندرية"],
    "alex": ["الإسكندرية", "الاسكندرية"],
    "hurghada": ["الغردقة"],
    "sharm": ["شرم الشيخ", "شرم"],
    "cairo": ["القاهرة"],
    "port said": ["بورسعيد", "بور سعيد"],
    "marsa alam": ["مرسى علم"],
    "marsa": ["مرسى علم"],
    "nuweiba": ["نويبع"],
    "makadi": ["مكادى"],
    "north coast": ["الساحل الشمالى", "الساحل"],
    "luxor": ["الأقصر"],
    "sokhna": ["العين السخنة", "السخنة"],
}

KB_CATEGORY_LABELS = {
    "services": "Services",
    "faq": "FAQ",
    "about": "About",
    "policies": "Policies",
    "destinations": "Destinations",
}

CONTENT_TYPE_ORDER = (
    "trips",
    "stations",
    "destinations",
    "services",
    "faq",
    "about",
    "policies",
)


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_pattern(term: str) -> str:
    return f"%{escape_like(term.strip())}%"


def _expand_search_terms(query: str, db: Session) -> list[str]:
    terms: list[str] = []
    q_lower = query.lower()

    for en_key, ar_names in DESTINATION_ALIASES.items():
        if en_key in q_lower:
            terms.extend(ar_names)

    for ar_names in DESTINATION_ALIASES.values():
        for ar in ar_names:
            if ar in query:
                terms.append(ar)

    for en_key, ar_names in STATION_ALIASES.items():
        if en_key in q_lower:
            terms.extend(ar_names)

    for route in active_routes():
        if route.origin in query:
            terms.append(route.origin)
        if route.destination in query:
            terms.append(route.destination)

    for station in active_stations():
        if station.name in query:
            terms.append(station.name)

    for dest in active_destinations():
        name = dest.name_ar
        if name in query:
            terms.append(name)
        short = name.replace("مدينة ", "")
        if short and short in query:
            terms.append(name)
            terms.append(short)

    stripped = query.strip()
    if len(stripped) <= 24:
        terms.append(stripped)

    for token in re.split(r"[\s,;–\-/|]+", stripped):
        token = token.strip()
        if len(token) >= 3 and token.lower() not in TRIP_KEYWORDS:
            terms.append(token)

    seen: set[str] = set()
    unique: list[str] = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def _mentions_trips(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in TRIP_KEYWORDS)


def _mentions_booking(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in BOOKING_KEYWORDS)


def _mentions_faq(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in FAQ_KEYWORDS)


def _mentions_policies(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in POLICY_KEYWORDS)


def _mentions_destination_topic(query: str) -> bool:
    q = query.lower()
    if any(k in q for k in DESTINATION_KEYWORDS):
        return True
    return _mentions_destination(query) and not _mentions_trips(query)


def _mentions_services(query: str) -> bool:
    q = query.lower()
    if any(k in q for k in SERVICE_KEYWORDS):
        return True
    return ("gobus" in q or "جوباص" in q) and any(
        word in q for word in ("service", "services", "mini", "lemo", "خدمة", "خدمات")
    )


def _mentions_general_company(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in GENERAL_COMPANY_KEYWORDS)


def _mentions_stations(query: str) -> bool:
    q = query.lower()
    if any(k in q for k in STATION_KEYWORDS):
        return True
    if "station" in q or "محطة" in q or "nearest" in q or "أقرب" in q:
        return any(alias in q for alias in STATION_ALIASES)
    return False


def _mentions_destination(query: str) -> bool:
    q = query.lower()
    if any(alias in q for alias in DESTINATION_ALIASES):
        return True
    return any(ar in query for names in DESTINATION_ALIASES.values() for ar in names)


TRAVEL_INTENT_HINTS = (
    "schedule", "trip", "price", "seat", "next", "travel", "go to", "going to",
    "from", "to ", "tomorrow", "today",
    "مواعيد", "رحلة", "رحلات", "سعر", "مقعد", "اسافر", "أسافر", "اروح", "أروح",
    "رايح", "ذاهب", "بكرة", "بكره", "غدا", "النهاردة", "من", "الى", "إلى",
)


def _should_include_trips(query: str, search_terms: list[str]) -> bool:
    if _mentions_booking(query) and not _mentions_trips(query):
        return False
    if _mentions_trips(query):
        return True
    # A named destination combined with any travel-intent phrasing → show trips.
    if _mentions_destination(query) and any(
        hint in query.lower() for hint in TRAVEL_INTENT_HINTS
    ):
        return True
    return False


def _trip_route_terms(search_terms: list[str]) -> list[str]:
    """Prefer origin/destination names over generic tokens for route matching."""
    route_terms: list[str] = []
    for term in search_terms:
        if len(term) >= 3 and term not in TRIP_KEYWORDS:
            route_terms.append(term)
    return route_terms[:6]


# Separator used to join conversation turns into a single ``fallback_text`` so the
# route resolver can split them back out and scan newest-first (ASCII record sep).
_HISTORY_SEP = "\x1e"


def _match_routes(db: Session, query_text: str, search_terms: list[str]) -> tuple[list[int], list[int]]:
    """Return (both_ids, single_ids): routes with both endpoints named vs one.

    Matching is done in Python with Arabic normalization so spelling variants
    (e.g. الاسكندرية vs الإسكندرية) still match, which exact SQL LIKE cannot do.
    """
    route_terms = _trip_route_terms(search_terms)
    if not route_terms:
        return [], []

    # Normalized haystack of the question plus all expanded terms (which include
    # Arabic translations of English city names from the alias maps).
    norm_terms = [normalize_arabic(t) for t in route_terms if t]
    haystack = normalize_arabic(query_text + " " + " ".join(route_terms))

    def _endpoint_mentioned(endpoint: str) -> bool:
        norm_ep = normalize_arabic(endpoint)
        if not norm_ep:
            return False
        if norm_ep in haystack:
            return True
        # Handle short mentions of multi-word endpoints (e.g. "شرم" → "شرم الشيخ").
        # Match whole words only, so prepositions like "الى" don't substring-match
        # inside an endpoint word such as "الشمالى".
        ep_words = set(norm_ep.split())
        return any(len(nt) >= 3 and nt in ep_words for nt in norm_terms)

    both_ids: list[int] = []
    single_ids: list[int] = []
    for route in active_routes():
        origin_hit = _endpoint_mentioned(route.origin)
        dest_hit = _endpoint_mentioned(route.destination)
        if origin_hit and dest_hit:
            both_ids.append(route.id)
        elif origin_hit or dest_hit:
            single_ids.append(route.id)

    return both_ids, single_ids


def _resolve_route_ids(
    db: Session,
    query_text: str,
    search_terms: list[str],
    *,
    fallback_text: str | None = None,
) -> list[int]:
    """Find route IDs for a trip query, preferring fully-specified routes.

    For follow-up questions that don't name a route ("the latest 5 trips"), or
    that only name one endpoint ambiguously, fall back to the route discussed in
    the recent conversation (``fallback_text``) so anaphora resolves correctly.
    """
    both_ids, single_ids = _match_routes(db, query_text, search_terms)
    if both_ids:
        return both_ids
    # The CURRENT turn naming a route (even one endpoint, e.g. "trip to Dahab")
    # always wins over conversation history — otherwise a route from an earlier
    # turn would hijack a clearly different new request.
    if single_ids:
        return single_ids

    # Only when the current turn names no route at all (e.g. "the latest 5") fall
    # back to the most recent remembered turn that did, newest-first.
    if fallback_text:
        turns = [t for t in fallback_text.split(_HISTORY_SEP) if t.strip()]
        for turn in reversed(turns):
            fb_both, _ = _match_routes(db, turn, _expand_search_terms(turn, db))
            if fb_both:
                return fb_both
        for turn in reversed(turns):
            _, fb_single = _match_routes(db, turn, _expand_search_terms(turn, db))
            if fb_single:
                return fb_single

    return []


# Superlative cues that mean "show the LAST/most distant trip" rather than the
# soonest one. Stored pre-normalized so Arabic hamza/alef variants all match.
_LATEST_KEYWORDS = {
    normalize_arabic(k)
    for k in ("latest", "last", "final", "furthest", "آخر", "أخر", "اخر", "أحدث", "احدث", "أبعد", "ابعد")
}


def _wants_latest_trip(query: str) -> bool:
    nq = normalize_arabic(query)
    return any(k and k in nq for k in _LATEST_KEYWORDS)


# Price-sort cues. "asc" → cheapest first, "desc" → most expensive first.
_CHEAPEST_KEYWORDS = {
    normalize_arabic(k)
    for k in ("cheapest", "cheaper", "lowest", "least expensive", "أرخص", "ارخص", "أقل سعر", "اقل سعر", "أرخص سعر")
}
_PRICIEST_KEYWORDS = {
    normalize_arabic(k)
    for k in ("most expensive", "priciest", "highest price", "dearest", "أغلى", "اغلى", "أعلى سعر", "اعلى سعر")
}


def _price_sort(query: str) -> str | None:
    nq = normalize_arabic(query)
    # Check "most expensive" before the generic — "expensive" alone is ambiguous.
    if any(k in nq for k in _PRICIEST_KEYWORDS):
        return "desc"
    if any(k in nq for k in _CHEAPEST_KEYWORDS):
        return "asc"
    return None


# Time like "8:30" must not be read as a trip count.
_TIME_RE = re.compile(r"\d{1,2}:\d{2}")
# A count right after an ordinal/imperative cue, e.g. "latest 5", "آخر 5", "show 3".
_COUNT_NEAR_RE = re.compile(
    r"(?:latest|last|first|top|show|give|me|earliest|soonest|cheapest|next"
    r"|اول|أول|اخر|آخر|اعطني|عايز|اريد|أريد|أحدث|احدث)\s+(\d{1,2})\b",
    re.IGNORECASE,
)
# A count immediately before the word trip(s), e.g. "5 trips", "5 رحلات".
_COUNT_BEFORE_TRIP_RE = re.compile(r"\b(\d{1,2})\s+(?:trips?|رحلات|رحلة)\b", re.IGNORECASE)

# Cues that signal an elliptical trip follow-up ("the latest 5", "the cheapest",
# "show 3 more") — i.e. a trip question that names neither a route nor the word
# "trip". Combined with a route remembered from the conversation, these let us
# still fetch fresh trip data instead of letting the model reuse stale history.
_TRIP_FOLLOWUP_CUES = {
    normalize_arabic(x)
    for x in (
        "latest", "last", "earliest", "soonest", "next", "first", "cheapest",
        "expensive", "more", "another", "other",
        "آخر", "اخر", "أول", "اول", "التالي", "أبكر", "ابكر", "أرخص", "ارخص",
        "أغلى", "اغلى", "المزيد", "كمان", "تاني", "تانى", "غيرها",
    )
}


def _is_trip_followup(query: str) -> bool:
    nq = normalize_arabic(query)
    if any(c and c in nq for c in _TRIP_FOLLOWUP_CUES):
        return True
    # A bare number ("5", "3") used as a follow-up after a trip listing.
    return bool(re.fullmatch(r"\s*\d{1,2}\s*", query))


def _trip_limit(query: str, default: int = 8, cap: int = 12) -> int:
    """Honor an explicit small count in the query (e.g. 'latest 5 trips').

    Only treats a number as a count when it follows an ordinal/imperative cue or
    immediately precedes the word "trip(s)", or the whole query is just a number.
    Times like "8:30" and ordinals like "the 5th" are ignored.
    """
    masked = _TIME_RE.sub(" ", query)
    for rx in (_COUNT_NEAR_RE, _COUNT_BEFORE_TRIP_RE):
        m = rx.search(masked)
        if m:
            n = int(m.group(1))
            if 1 <= n <= cap:
                return n
    stripped = query.strip()
    if re.fullmatch(r"\d{1,2}", stripped):
        n = int(stripped)
        if 1 <= n <= cap:
            return n
    return default


def _compile_sql(db: Session, query) -> str:
    """Render a SQLAlchemy query as an executable SQL string for display."""
    try:
        compiled = query.statement.compile(
            dialect=db.bind.dialect, compile_kwargs={"literal_binds": True}
        )
        return str(compiled).strip()
    except Exception:  # pragma: no cover - display-only, never fail the chat
        return ""


def _term_matches(nt: str, text_norm: str) -> bool:
    """Match a normalized term in text. Short single-word terms (< 5 chars) must
    match on a word boundary so generic words like "بين"/"اللي" don't substring-hit
    inside longer words (e.g. "مكتبين"); longer terms / phrases allow substring."""
    if not nt:
        return False
    if len(nt) >= 5 or " " in nt:
        return nt in text_norm
    return re.search(rf"(?<!\w){re.escape(nt)}(?!\w)", text_norm) is not None


def _query_matches_station(db: Session, query_text: str, search_terms: list[str]) -> bool:
    """True when the query names a known station — by name OR address/area.

    Lets bare station names ("التجمع الخامس") or area mentions ("شارع التسعين")
    trigger station retrieval even without an explicit "station/nearest" keyword.
    Uses the same distinctive (stopword-filtered) terms as the station fetch so
    generic words like "شارع" alone don't match every station.
    """
    terms = _station_search_terms(search_terms)
    if not terms:
        return False
    norm_terms = [normalize_arabic(t) for t in terms]
    for station in active_stations():
        norm_name = normalize_arabic(station.name)
        norm_addr = normalize_arabic(station.description or "")
        if any(_term_matches(nt, norm_name) or _term_matches(nt, norm_addr) for nt in norm_terms):
            return True
    return False


def _no_trips_hint(db: Session, *, limit: int = 8) -> list[str]:
    """A single context block listing real active routes when no trip matched.

    Lets the model suggest valid alternatives instead of a bare "I don't have
    that", without implying any trip exists for the asked route.
    """
    routes = active_routes()[:limit]
    names = "، ".join(f"{r.origin} → {r.destination}" for r in routes)
    if not names:
        return []
    return [
        "[Trips] (no matching upcoming trips found for the requested route). "
        f"Active routes you can ask about: {names}"
    ]


def _trip_ordering(query_text: str) -> tuple[list, bool]:
    """Decide ORDER BY columns and whether to reverse rows for display.

    Precedence: explicit price sort > latest/most-distant > default soonest.
    """
    price_dir = _price_sort(query_text)
    if price_dir == "asc":
        return [Trip.price_egp.asc(), Trip.trip_date.asc(), Trip.departure_time.asc()], False
    if price_dir == "desc":
        return [Trip.price_egp.desc(), Trip.trip_date.asc(), Trip.departure_time.asc()], False
    if _wants_latest_trip(query_text):
        # Fetch the most distant trips, then reverse so the block reads
        # chronologically with the latest trip last.
        return [Trip.trip_date.desc(), Trip.departure_time.desc()], True
    return [Trip.trip_date.asc(), Trip.departure_time.asc()], False


def _fetch_trip_blocks(
    db: Session,
    query_text: str,
    search_terms: list[str],
    *,
    limit: int | None = None,
    debug: dict | None = None,
    fallback_text: str | None = None,
) -> list[str]:
    route_ids = _resolve_route_ids(db, query_text, search_terms, fallback_text=fallback_text)
    if not route_ids:
        return _no_trips_hint(db)

    if limit is None:
        limit = _trip_limit(query_text)

    order_cols, reverse_for_display = _trip_ordering(query_text)

    query = (
        db.query(Trip)
        .join(Route)
        .options(
            joinedload(Trip.route),
            joinedload(Trip.departure_station),
            joinedload(Trip.arrival_station),
        )
        .filter(Route.is_active.is_(True))
        .filter(Trip.route_id.in_(route_ids))
        .filter(Trip.trip_date >= date.today())
        .filter(Trip.status.in_(["open", "full"]))
        .order_by(*order_cols)
        .limit(limit)
    )

    if debug is not None:
        debug["trips_sql"] = _compile_sql(db, query)

    trips = [t for t in query.all() if t.route]
    if reverse_for_display:
        trips = list(reversed(trips))

    # De-duplicate trips identical on the user-visible fields (e.g. the same run
    # offered under more than one service code) so the table has no repeated rows.
    rows: list[Trip] = []
    seen: set[tuple] = set()
    for trip in trips:
        key = (
            trip.route.origin,
            trip.route.destination,
            trip.trip_date,
            trip.departure_time,
            trip.bus_class,
            trip.price_egp,
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(trip)

    if not rows:
        return _no_trips_hint(db)

    # Structured rows for deterministic frontend rendering (a table), so layout +
    # accuracy never depend on the model. The LLM just writes a one-line intro.
    if debug is not None:
        debug["trips"] = [
            {
                "origin": t.route.origin,
                "destination": t.route.destination,
                "departure_station": t.departure_station.name if t.departure_station else None,
                "arrival_station": t.arrival_station.name if t.arrival_station else None,
                "date": t.trip_date.isoformat(),
                "departure": t.departure_time.strftime("%H:%M"),
                "arrival": t.arrival_time.strftime("%H:%M"),
                "bus_class": t.bus_class,
                "available_seats": t.available_seats,
                "total_seats": t.total_seats,
                "price_egp": float(t.price_egp),
                "bookable": bool(t.is_bookable and t.status == "open"),
            }
            for t in rows
        ]

    routes_shown = "، ".join(sorted({f"{t.route.origin} → {t.route.destination}" for t in rows}))
    return [
        f"[Trips] {len(rows)} matching trip(s) for {routes_shown} are shown to the user "
        "as a table (date, time, class, seats, price). Reply with only a short one-line "
        "intro; do NOT list the trips or build a table yourself."
    ]


def _merge_context_parts(*groups: list[str], limit: int = 10) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for block in group:
            if block in seen:
                continue
            seen.add(block)
            merged.append(block)
            if len(merged) >= limit:
                return "\n\n---\n\n".join(merged)
    return "\n\n---\n\n".join(merged)


def _detect_content_intents(query: str, search_terms: list[str]) -> set[str]:
    """Map the user question to KB content types to load."""
    intents: set[str] = set()

    if _should_include_trips(query, search_terms):
        intents.add("trips")
    if _mentions_stations(query):
        intents.add("stations")
    if _mentions_destination_topic(query):
        intents.add("destinations")
    if _mentions_services(query):
        intents.add("services")
    if _mentions_general_company(query):
        intents.add("about")
    if _mentions_policies(query):
        intents.add("policies")
    if _mentions_booking(query) or _mentions_faq(query):
        intents.add("faq")
    if "gobus" in query.lower() or "جوباص" in query:
        if not intents or intents == {"faq"}:
            intents.add("faq")

    if not intents:
        intents.add("faq")
        if _mentions_destination(query):
            intents.add("destinations")
        if _should_include_trips(query, search_terms):
            intents.add("trips")

    return intents


def _fetch_kb_category_blocks(
    db: Session,
    category_code: str,
    search_terms: list[str],
    *,
    article_limit: int = 4,
    max_chars: int = 4000,
) -> list[str]:
    category = db.query(KbCategory).filter(KbCategory.code == category_code).first()
    if not category:
        return []

    label = KB_CATEGORY_LABELS.get(category_code, category.name_ar)
    base_query = (
        db.query(KbArticle)
        .options(joinedload(KbArticle.category))
        .filter(KbArticle.category_id == category.id, KbArticle.is_active.is_(True))
    )

    articles: list[KbArticle] = []
    if search_terms:
        article_filters = []
        for term in search_terms:
            p = _like_pattern(term)
            article_filters.append(KbArticle.title.like(p))
            article_filters.append(KbArticle.content.like(p))
        articles = base_query.filter(or_(*article_filters)).limit(article_limit).all()

    if not articles:
        articles = base_query.order_by(KbArticle.id).limit(article_limit).all()

    blocks: list[str] = []
    for article in articles:
        blocks.append(f"[{label}] {article.title}\n{article.content[:max_chars]}")
    return blocks


# Generic words that appear in many station names/addresses; matching on them
# would return almost every station, so they're excluded from station search.
_STATION_SEARCH_STOPWORDS = {
    normalize_arabic(w)
    for w in (
        "محطة", "محطه", "جوباص", "جو", "باص", "مكتب", "موقف",
        "شارع", "طريق", "ميدان", "منطقة", "مدينة", "مدينه", "حي", "الحي",
        "بجوار", "امام", "أمام", "مول", "كوبري", "بنزينة", "خلف", "داخل", "علي", "على",
        "الاركاب", "الإركاب", "الانزال", "الإنزال", "مواعيد", "العمل",
        "الاقرب", "الأقرب", "اقرب", "أقرب", "قريب", "الى", "إلى", "في", "من", "لا", "يوجد",
        "station", "stations", "nearest", "closest", "near", "the", "to", "in",
        "on", "is", "there", "map", "location", "where", "street", "gobus",
        # Generic question/conjunction words + service/class terms that are NOT stations.
        "بين", "ايه", "إيه", "الفرق", "فرق", "ماهو", "ما", "هو", "هي", "عايز", "عاوز",
        "standard", "elite", "business", "gomini", "golemo", "difference", "between",
        "class", "classes", "service", "services", "price", "prices", "سعر", "اسعار", "فئات", "فئة",
        "اتوبيس", "الاتوبيس", "الأتوبيس", "اوتوبيس", "الاوتوبيس", "اتوبيسات", "المتاحة", "متاح", "متاحة",
    )
}


def _station_search_terms(search_terms: list[str]) -> list[str]:
    """Distinctive terms only — drop generic address/stopwords that match everything."""
    out: list[str] = []
    seen: set[str] = set()
    for term in search_terms:
        norm = normalize_arabic(term)
        if len(norm) < 3 or norm in _STATION_SEARCH_STOPWORDS:
            continue
        # Drop multi-word phrases that are entirely generic (e.g. "اقرب محطة").
        words = [w for w in norm.split() if w not in _STATION_SEARCH_STOPWORDS and len(w) >= 3]
        if not words:
            continue
        if norm not in seen:
            seen.add(norm)
            out.append(term)
    return out


def _clean_station_address(description: str | None) -> str:
    """Strip the inline 'مواعيد العمل ...' suffix some descriptions carry."""
    text = (description or "").strip()
    text = re.split(r"مواعيد\s*الع", text)[0]
    return text.strip(" -\n")


def _fetch_station_blocks(
    db: Session,
    query: str,
    search_terms: list[str],
    *,
    limit: int = 5,
    debug: dict | None = None,
) -> list[str]:
    terms = _station_search_terms(search_terms)
    if not terms:
        return []

    # Match in Python with Arabic normalization (handles ة/ه, alef variants etc.
    # that exact SQL LIKE misses). Prefer name matches; then the representative
    # station for a named city; only then fall back to an address-text match.
    norm_terms = [normalize_arabic(t) for t in terms]
    name_matches: list[Station] = []
    addr_matches: list[Station] = []
    for station in active_stations():
        norm_name = normalize_arabic(station.name)
        norm_addr = normalize_arabic(station.description or "")
        if any(_term_matches(nt, norm_name) for nt in norm_terms):
            name_matches.append(station)
        elif any(_term_matches(nt, norm_addr) for nt in norm_terms):
            addr_matches.append(station)

    # City-level queries ("the Alexandria station") rarely match a station NAME
    # (stations are area-named). Map the city to its main station so we don't fall
    # through to an unrelated station that merely mentions the city in its address.
    city_matches: list[Station] = []
    if not name_matches:
        mapped_names = {
            CITY_STATION_NAMES[city]
            for city in CITY_STATION_NAMES
            if any(nt and normalize_arabic(city) in nt for nt in norm_terms)
        }
        if mapped_names:
            city_matches = [s for s in active_stations() if s.name in mapped_names]

    stations = (name_matches or city_matches or addr_matches)[:limit]
    if not stations:
        return []

    # Structured station data for deterministic frontend rendering (a card),
    # so the layout never depends on the model's formatting.
    if debug is not None:
        debug["stations"] = [
            {
                "name": s.name,
                "address": _clean_station_address(s.description),
                "working_hours": s.working_hours or "",
                "map_url": s.map_url or "",
            }
            for s in stations
        ]

    # The full station details (address, working hours, map) are rendered to the user
    # as a card from debug["stations"]. We don't put them in the model text (so it
    # can't duplicate or mangle them) — but the model MUST treat them as available and
    # never refuse, since the user can see the card right below the reply.
    names = "، ".join(s.name for s in stations)
    return [
        f"[Stations] The full details for {names} (address, working hours, and a map "
        "link) ARE available and are shown to the user as a card directly below your "
        "reply. Answer affirmatively with ONE short friendly line that points to it "
        "(e.g. \"Here are the station details:\" / \"تفضل تفاصيل المحطة:\"). Do NOT repeat "
        "the address/hours/map in your text. NEVER say you can't provide, don't have, or "
        "to check the app for the address — it is already displayed in the card."
    ]


_DESTINATION_LIST_CUES = {
    normalize_arabic(c)
    for c in (
        "destinations", "which destinations", "what destinations", "serve", "serves",
        "cities", "places", "routes", "وجهات", "الوجهات", "اماكن", "الاماكن", "مدن",
        "تخدم", "بتروح", "بتروحوا", "تروحوا", "وين", "فين",
    )
}


def _wants_destination_list(query: str) -> bool:
    nq = normalize_arabic(query)
    return any(c and c in nq for c in _DESTINATION_LIST_CUES)


def _all_route_destinations(db: Session) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for route in active_routes():
        if route.destination and route.destination not in seen:
            seen.add(route.destination)
            out.append(route.destination)
    return out


def _fetch_destination_blocks(
    db: Session,
    query: str,
    search_terms: list[str],
    *,
    limit: int = 3,
    max_chars: int = 4000,
    debug: dict | None = None,
) -> list[str]:
    blocks: list[str] = []

    # "Which destinations does GoBus serve?" → render the REAL list deterministically
    # as chips (debug["destinations"]); the model only writes a one-line intro. This
    # avoids the model substituting general-knowledge cities.
    if _wants_destination_list(query):
        dests = _all_route_destinations(db)
        if dests:
            if debug is not None:
                debug["destinations"] = dests
            return [
                "[Destinations] The full list of GoBus destinations is shown to the user "
                "as chips. Reply with only a short one-line intro and do NOT list the "
                "destinations yourself."
            ]

    dest_filters = []
    for term in search_terms:
        p = _like_pattern(term)
        dest_filters.extend([Destination.name_ar.like(p), Destination.content.like(p)])
    destinations = (
        db.query(Destination)
        .filter(Destination.is_active.is_(True))
        .filter(or_(*dest_filters))
        .limit(limit)
        .all()
        if dest_filters
        else []
    )
    for dest in destinations:
        blocks.append(f"[Destinations] {dest.name_ar}\n{dest.content[:max_chars]}")

    blocks.extend(
        _fetch_kb_category_blocks(db, "destinations", search_terms, article_limit=2, max_chars=max_chars)
    )
    return blocks


def _fetch_service_blocks(db: Session, search_terms: list[str]) -> list[str]:
    blocks = _fetch_kb_category_blocks(db, "services", search_terms, article_limit=6)
    if blocks:
        return blocks

    services = active_services()
    for svc in services:
        detail = "Full data available" if svc.has_detailed_data else "General info only"
        blocks.append(
            f"[Services] {svc.name_ar} ({svc.name_en}) - {svc.code}\n"
            f"{svc.description}\n({detail})"
        )
    return blocks


def retrieve_context(
    db: Session,
    query: str,
    limit: int = 10,
    *,
    debug: dict | None = None,
    history_text: str | None = None,
    extra_query: str | None = None,
) -> str:
    """Build the KB context string for a user query.

    Pass a mutable ``debug`` dict to capture diagnostic info (currently the
    compiled trips SQL under key ``trips_sql``) for display in the UI.
    ``history_text`` is recent conversation text used to resolve the route for
    follow-up trip questions that don't name one ("the latest 5 trips").
    ``extra_query`` is an LLM-normalized version of the question (EN/Franco place
    names translated to Arabic). It is used ONLY to add place-matching search
    terms — intent detection and qualifiers always use the ORIGINAL query, so a
    bad rewrite can never change what kind of answer the user gets.
    """
    q = query.strip()
    if not q:
        return ""

    search_terms = _expand_search_terms(q, db)
    # Merge in terms from the normalized rewrite (for matching only).
    if extra_query and extra_query.strip() and extra_query.strip() != q:
        seen = set(search_terms)
        for term in _expand_search_terms(extra_query.strip(), db):
            if term not in seen:
                seen.add(term)
                search_terms.append(term)
    intents = _detect_content_intents(q, search_terms)

    # Elliptical trip follow-up ("the latest 5") with a route remembered from the
    # conversation → treat as a trip query so we fetch fresh data rather than
    # letting the model reconstruct trips from earlier messages.
    if "trips" not in intents and history_text and _is_trip_followup(q):
        fb_both, fb_single = _match_routes(db, history_text, _expand_search_terms(history_text, db))
        if fb_both or fb_single:
            intents.add("trips")

    # A bare station name or area mention ("التجمع الخامس", "شارع التسعين") should
    # load station data even without an explicit "station/nearest" keyword — but
    # NOT for trip/destination questions where the place is a route endpoint
    # (e.g. "next trip to Dahab" must not show a Dahab station card).
    if (
        "stations" not in intents
        and "trips" not in intents
        and "destinations" not in intents
        and _query_matches_station(db, q, search_terms)
    ):
        intents.add("stations")

    if _mentions_stations(q):
        search_terms.extend(["محطة", "station", "map", "خريطة"])
    if _mentions_general_company(q):
        search_terms.extend(["جوباص", "جو باص", "شركة", "مساهمة", "gobus", "about", "company"])
    if _mentions_booking(q):
        search_terms.extend(["حجز", "booking", "ticket", "تذكرة"])

    groups: list[list[str]] = []
    for content_type in CONTENT_TYPE_ORDER:
        if content_type not in intents:
            continue
        if content_type == "trips":
            groups.append(
                _fetch_trip_blocks(db, q, search_terms, debug=debug, fallback_text=history_text)
            )
        elif content_type == "stations":
            groups.append(_fetch_station_blocks(db, q, search_terms, debug=debug))
        elif content_type == "destinations":
            groups.append(_fetch_destination_blocks(db, q, search_terms, debug=debug))
        elif content_type == "services":
            groups.append(_fetch_service_blocks(db, search_terms))
        elif content_type == "faq":
            faq_blocks = _fetch_kb_category_blocks(db, "faq", search_terms, article_limit=5)
            if _mentions_booking(q) and not any("حجز" in b or "book" in b.lower() for b in faq_blocks):
                booking = db.query(KbArticle).filter(KbArticle.slug == "faq-booking-gobus").first()
                if booking:
                    faq_blocks.insert(
                        0,
                        f"[FAQ] {booking.title}\n{booking.content[:4000]}",
                    )
            groups.append(faq_blocks)
        elif content_type == "about":
            groups.append(_fetch_kb_category_blocks(db, "about", search_terms, article_limit=6))
        elif content_type == "policies":
            groups.append(_fetch_kb_category_blocks(db, "policies", search_terms, article_limit=4))

    return _merge_context_parts(*groups, limit=limit)
