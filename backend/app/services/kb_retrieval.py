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
from app.services.chat_understanding import ChatUnderstanding
from app.utils.text_utils import normalize_arabic

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
        if len(token) >= 3:
            terms.append(token)

    seen: set[str] = set()
    unique: list[str] = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def _trip_route_terms(search_terms: list[str]) -> list[str]:
    """Prefer origin/destination names over generic tokens for route matching."""
    return [term for term in search_terms if len(term) >= 3][:6]


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


def _trip_ordering(understanding: ChatUnderstanding) -> tuple[list, bool]:
    """Decide ORDER BY columns and whether to reverse rows for display."""
    sort = understanding.trip_sort or "soonest"
    if sort == "cheapest":
        return [Trip.price_egp.asc(), Trip.trip_date.asc(), Trip.departure_time.asc()], False
    if sort == "priciest":
        return [Trip.price_egp.desc(), Trip.trip_date.asc(), Trip.departure_time.asc()], False
    if sort == "latest":
        return [Trip.trip_date.desc(), Trip.departure_time.desc()], True
    return [Trip.trip_date.asc(), Trip.departure_time.asc()], False


def _trip_limit(understanding: ChatUnderstanding, default: int = 8, cap: int = 12) -> int:
    n = understanding.trip_limit
    if n is not None and 1 <= n <= cap:
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


def _fetch_trip_blocks(
    db: Session,
    query_text: str,
    search_terms: list[str],
    *,
    limit: int | None = None,
    debug: dict | None = None,
    fallback_text: str | None = None,
    understanding: ChatUnderstanding | None = None,
) -> list[str]:
    u = understanding or ChatUnderstanding()
    route_ids = _resolve_route_ids(db, query_text, search_terms, fallback_text=fallback_text)
    if not route_ids:
        return _no_trips_hint(db)

    if limit is None:
        limit = _trip_limit(u)

    order_cols, reverse_for_display = _trip_ordering(u)

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
        f"[Trips] {len(rows)} matching trip(s) for {routes_shown} with live prices in EGP "
        "ARE available and are shown to the user as a table directly below your reply "
        "(date, time, class, seats, price). Answer affirmatively with ONE short friendly "
        "intro line (e.g. \"Here are the trips:\" / \"إليك الرحلات:\"). Do NOT list trips "
        "or build a table yourself. NEVER say you can't provide prices/schedules, don't "
        "have the data, or tell them to check the app or website for prices — the table "
        "already shows every price."
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
        # Generic English words that substring-match station addresses (e.g. "Best Way").
        "way", "make", "complain", "complaint", "have", "help", "assist", "support",
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
    skip_structured: bool = False,
    understanding: ChatUnderstanding | None = None,
) -> str:
    """Build the KB context string for a user query.

    Routing (what to fetch) comes from ``understanding`` — an LLM classification
    of the message plus conversation context. ``extra_query`` adds normalized
    place-matching search terms from the understanding/search rewrite step.
    """
    q = query.strip()
    if not q:
        return ""

    u = understanding or ChatUnderstanding(search_query=q)
    primary_query = (u.search_query or q).strip()
    search_terms = _expand_search_terms(primary_query, db)
    if extra_query and extra_query.strip() and extra_query.strip() not in {q, primary_query}:
        seen = set(search_terms)
        for term in _expand_search_terms(extra_query.strip(), db):
            if term not in seen:
                seen.add(term)
                search_terms.append(term)
    # Also expand the raw user message so colloquial phrasing still matches routes.
    if primary_query != q:
        seen = set(search_terms)
        for term in _expand_search_terms(q, db):
            if term not in seen:
                seen.add(term)
                search_terms.append(term)

    intents = set(u.content_intents)
    if not intents:
        intents = {"faq"}

    if not u.wants_live_trips:
        intents.discard("trips")

    if skip_structured or u.in_complaint_flow:
        intents -= {"trips", "stations", "destinations"}

    # Follow-up trip question with route from conversation history.
    if u.use_history_for_route and "trips" not in intents and history_text:
        fb_both, fb_single = _match_routes(db, history_text, _expand_search_terms(history_text, db))
        if fb_both or fb_single:
            intents.add("trips")

    if "stations" in intents:
        search_terms.extend(["محطة", "station", "map", "خريطة"])
    if "about" in intents:
        search_terms.extend(["جوباص", "جو باص", "شركة", "مساهمة", "gobus", "about", "company"])
    if u.booking_related or "faq" in intents:
        search_terms.extend(["حجز", "booking", "ticket", "تذكرة"])

    route_history = history_text

    groups: list[list[str]] = []
    live_trips = False
    live_stations = False
    for content_type in CONTENT_TYPE_ORDER:
        if content_type not in intents:
            continue
        # FAQ articles often say "check the app for prices" — that contradicts a live
        # trips/stations table already rendered below the reply.
        if live_trips and content_type == "faq":
            continue
        if live_stations and content_type == "faq":
            continue
        if content_type == "trips":
            trip_blocks = _fetch_trip_blocks(
                db,
                primary_query,
                search_terms,
                debug=debug,
                fallback_text=route_history,
                understanding=u,
            )
            groups.append(trip_blocks)
            if debug and debug.get("trips"):
                live_trips = True
        elif content_type == "stations":
            station_blocks = _fetch_station_blocks(db, primary_query, search_terms, debug=debug)
            groups.append(station_blocks)
            if debug and debug.get("stations"):
                live_stations = True
        elif content_type == "destinations":
            groups.append(_fetch_destination_blocks(db, primary_query, search_terms, debug=debug))
        elif content_type == "services":
            svc_blocks = _fetch_service_blocks(db, search_terms)
            if u.wants_service_info:
                bus_classes = (
                    db.query(KbArticle)
                    .filter(KbArticle.slug == "faq-bus-classes", KbArticle.is_active.is_(True))
                    .first()
                )
                if bus_classes:
                    block = f"[FAQ] {bus_classes.title}\n{bus_classes.content[:4000]}"
                    if not any(bus_classes.title in b for b in svc_blocks):
                        svc_blocks.insert(0, block)
            groups.append(svc_blocks)
        elif content_type == "faq":
            faq_blocks = _fetch_kb_category_blocks(db, "faq", search_terms, article_limit=5)
            if u.booking_related and not any("حجز" in b or "book" in b.lower() for b in faq_blocks):
                booking = db.query(KbArticle).filter(KbArticle.slug == "faq-booking-gobus").first()
                if booking:
                    faq_blocks.insert(
                        0,
                        f"[FAQ] {booking.title}\n{booking.content[:4000]}",
                    )
            if u.wants_service_info:
                bus_classes = (
                    db.query(KbArticle)
                    .filter(KbArticle.slug == "faq-bus-classes", KbArticle.is_active.is_(True))
                    .first()
                )
                if bus_classes and not any(bus_classes.title in b for b in faq_blocks):
                    faq_blocks.insert(
                        0,
                        f"[FAQ] {bus_classes.title}\n{bus_classes.content[:4000]}",
                    )
            groups.append(faq_blocks)
        elif content_type == "about":
            groups.append(_fetch_kb_category_blocks(db, "about", search_terms, article_limit=6))
        elif content_type == "policies":
            groups.append(_fetch_kb_category_blocks(db, "policies", search_terms, article_limit=4))

    return _merge_context_parts(*groups, limit=limit)
