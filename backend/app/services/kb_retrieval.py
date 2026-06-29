"""Knowledge base retrieval helpers for chat context."""

import difflib
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
from app.utils.text_utils import normalize_arabic, romanized_key

VALID_TRIP_SORT = frozenset({"soonest", "latest", "cheapest", "priciest"})

STATION_ALIASES: dict[str, list[str]] = {
    "fifth settlement": ["التجمع الخامس"],
    "5th settlement": ["التجمع الخامس"],
    "tagamoa el khames": ["التجمع الخامس"],
    "tagamo3 el khames": ["التجمع الخامس"],
    "el tagamo3 el khames": ["التجمع الخامس"],
    "street 90": ["شارع التسعين", "التجمع الخامس"],
    "90th street": ["شارع التسعين", "التجمع الخامس"],
    "rehab": ["مدينة الرحاب", "الرحاب"],
    "el rehab": ["مدينة الرحاب", "الرحاب"],
    "sheikh zayed": ["الشيخ زايد", "هايبر وان (الشيخ زايد)"],
    "giza": ["الجيزة", "جيزة"],
    "madinaty": ["مدينتي"],
    "madinty": ["مدينتي"],
    "heliopolis": ["مصر الجديدة", "الماظة", "الألماظة"],
    "nasr city": ["مدينة نصر", "محطة مدينه نصر"],
    "maadi": ["المعادي"],
    "october": ["أكتوبر", "السادس من أكتوبر", "6 اكتوبر"],
    "6th of october": ["السادس من اكتوبر"],
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

# Areas GoBus does NOT depart from → the nearest city that DOES (the recommended
# boarding point). Used when a customer names an origin with no route so we can
# still show them where to board and the trips from there. Values MUST be real
# route origins (so a route resolves) and have an entry in CITY_STATION_NAMES.
NEAREST_ORIGIN_REGION: dict[str, str] = {
    # Greater Cairo metro → board in Cairo (عبد المنعم رياض)
    "الجيزة": "القاهرة",
    "جيزة": "القاهرة",
    "giza": "القاهرة",
    "الهرم": "القاهرة",
    "haram": "القاهرة",
    "فيصل": "القاهرة",
    "6 اكتوبر": "القاهرة",
    "السادس من اكتوبر": "القاهرة",
    "اكتوبر": "القاهرة",
    "october": "القاهرة",
    "الشيخ زايد": "القاهرة",
    "sheikh zayed": "القاهرة",
    "التجمع الخامس": "القاهرة",
    "التجمع": "القاهرة",
    "fifth settlement": "القاهرة",
    "مدينة نصر": "القاهرة",
    "nasr city": "القاهرة",
    "المعادي": "القاهرة",
    "maadi": "القاهرة",
    "حلوان": "القاهرة",
    "helwan": "القاهرة",
    "مصر الجديدة": "القاهرة",
    "heliopolis": "القاهرة",
    "الرحاب": "القاهرة",
    "rehab": "القاهرة",
    "مدينتي": "القاهرة",
    "madinaty": "القاهرة",
    "العبور": "القاهرة",
    "الشروق": "القاهرة",
    "بدر": "القاهرة",
    "بنها": "القاهرة",
    "القليوبية": "القاهرة",
    "شبرا": "القاهرة",
    # Alexandria area → board in Alexandria (سيدي جابر _ سموحة)
    "برج العرب": "الإسكندرية",
    "borg el arab": "الإسكندرية",
    "العجمي": "الإسكندرية",
    "ابو قير": "الإسكندرية",
    "ميامي": "الإسكندرية",
}

# Origin prepositions (Arabic + Franco/English) that mark the city the customer is
# departing FROM, so "to Giza" (a destination) never triggers a boarding swap.
_ORIGIN_MARKER = r"(?:from|frm|mn|men|min|m3a|من|مـن)"

KB_CATEGORY_LABELS = {
    "services": "Services",
    "faq": "FAQ",
    "about": "About",
    "policies": "Policies",
    "destinations": "Destinations",
}

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

    # Origin follow-up ("I'm from Cairo") + destination in history ("trip to Alex")
    # should resolve Cairo→Alexandria, not every route touching Cairo. Only merge with
    # history when the CURRENT turn names at least one endpoint — otherwise a pure
    # follow-up ("the latest 5") would union every route in history instead of using
    # the most recent one (handled by the newest-first scan below).
    if fallback_text and single_ids:
        combined_text = query_text + _HISTORY_SEP + fallback_text
        combined_terms = list(search_terms)
        seen_terms = set(combined_terms)
        for turn in fallback_text.split(_HISTORY_SEP):
            turn = turn.strip()
            if not turn:
                continue
            for term in _expand_search_terms(turn, db):
                if term not in seen_terms:
                    seen_terms.add(term)
                    combined_terms.append(term)
        comb_both, _ = _match_routes(db, combined_text, combined_terms)
        if comb_both:
            return comb_both

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


def _trip_ordering(sort: str | None) -> tuple[list, bool]:
    """Decide ORDER BY columns and whether to reverse rows for display."""
    sort = sort if sort in VALID_TRIP_SORT else "soonest"
    if sort == "cheapest":
        return [Trip.price_egp.asc(), Trip.trip_date.asc(), Trip.departure_time.asc()], False
    if sort == "priciest":
        return [Trip.price_egp.desc(), Trip.trip_date.asc(), Trip.departure_time.asc()], False
    if sort == "latest":
        return [Trip.trip_date.desc(), Trip.departure_time.desc()], True
    return [Trip.trip_date.asc(), Trip.departure_time.asc()], False


def _trip_limit(limit: int | None, default: int = 8, cap: int = 12) -> int:
    if limit is not None and 1 <= limit <= cap:
        return limit
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


def _route_origin_city(route_id: int) -> str | None:
    for route in active_routes():
        if route.id == route_id:
            return route.origin
    return None


def _station_for_city(city: str) -> Station | None:
    """The canonical boarding station record for a route-origin city."""
    name = CITY_STATION_NAMES.get(city)
    if not name:
        return None
    for station in active_stations():
        if station.name == name:
            return station
    return None


def _mentioned_unserved_origin(query_text: str) -> tuple[str, str] | None:
    """Detect a departure city the customer named that GoBus does NOT serve.

    Returns (mentioned_area, nearest_origin_city) or None. The area must follow an
    origin marker ("from"/"mn"/"من") so a *destination* ("to Giza") is never treated
    as a boarding swap.
    """
    norm_query = normalize_arabic(query_text)
    lower_query = query_text.lower()
    for area, origin_city in NEAREST_ORIGIN_REGION.items():
        if re.search(r"[؀-ۿ]", area):
            hay, needle = norm_query, normalize_arabic(area)
        else:
            hay, needle = lower_query, area.lower()
        if not needle or needle not in hay:
            continue
        if re.search(rf"{_ORIGIN_MARKER}\s+(?:\S+\s+){{0,2}}{re.escape(needle)}", hay):
            return area, origin_city
    return None


def _resolve_boarding_recommendation(query_text: str, route_ids: list[int]) -> dict | None:
    """When the customer named an unserved departure city, pick the nearest GoBus
    origin that reaches the destination and recommend its boarding station."""
    found = _mentioned_unserved_origin(query_text)
    if not found:
        return None
    mentioned_area, nearest_city = found

    # Prefer the nearest valid origin's route to the destination when it serves it;
    # otherwise fall back to whatever origin does serve the destination.
    nearest_route_ids = [rid for rid in route_ids if _route_origin_city(rid) == nearest_city]
    chosen_ids = nearest_route_ids or route_ids
    actual_origin = _route_origin_city(chosen_ids[0]) if chosen_ids else None
    if not actual_origin or actual_origin == mentioned_area:
        return None
    return {
        "mentioned_area": mentioned_area,
        "origin_city": actual_origin,
        "station": _station_for_city(actual_origin),
        "route_ids": chosen_ids,
    }


def _fetch_trip_blocks(
    db: Session,
    query_text: str,
    search_terms: list[str],
    *,
    sort: str = "soonest",
    bus_class: str | None = None,
    limit: int | None = None,
    debug: dict | None = None,
    fallback_text: str | None = None,
) -> list[str]:
    route_ids = _resolve_route_ids(db, query_text, search_terms, fallback_text=fallback_text)
    if not route_ids:
        return _no_trips_hint(db)

    # If the customer named a city GoBus doesn't depart from, narrow the trips to the
    # nearest valid origin so the table matches the boarding station we recommend.
    recommendation = _resolve_boarding_recommendation(query_text, route_ids)
    if recommendation:
        route_ids = recommendation["route_ids"]

    limit = _trip_limit(limit)

    order_cols, reverse_for_display = _trip_ordering(sort)

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
    )
    if bus_class:
        query = query.filter(Trip.bus_class == bus_class)

    query = query.order_by(*order_cols).limit(limit)

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
        if bus_class:
            routes = active_routes()
            route_label = "، ".join(
                f"{r.origin} → {r.destination}"
                for r in routes
                if r.id in route_ids
            ) or "the requested route"
            return [
                f"[Trips] (no matching upcoming {bus_class} class trips found for {route_label}). "
                "Tell the user plainly and suggest another class or date if helpful."
            ]
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

    blocks: list[str] = []

    # Boarding recommendation: GoBus doesn't depart from the city the customer named,
    # so surface the nearest origin's station card + a note explaining the swap.
    station = recommendation["station"] if recommendation else None
    if recommendation and station is not None:
        if debug is not None:
            debug["stations"] = [
                {
                    "name": station.name,
                    "address": _clean_station_address(station.description),
                    "working_hours": station.working_hours or "",
                    "map_url": station.map_url or "",
                }
            ]
            debug["boarding"] = {
                "mentioned_area": recommendation["mentioned_area"],
                "origin_city": recommendation["origin_city"],
                "station_name": station.name,
            }
        blocks.append(
            f"[Boarding] GoBus has NO departures from {recommendation['mentioned_area']}; "
            f"the nearest boarding station is {station.name} in {recommendation['origin_city']} "
            "(shown as a card below). The trips below depart from there."
        )

    routes_shown = "، ".join(sorted({f"{t.route.origin} → {t.route.destination}" for t in rows}))
    class_note = f" ({bus_class} class only)" if bus_class else ""
    blocks.append(
        f"[Trips] {len(rows)} matching trip(s) for {routes_shown}{class_note} are shown to the user "
        "as a table below (date, time, class, seats, price in EGP)."
    )
    return blocks


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
        "working", "hours", "hour", "open", "opening", "schedule", "time", "times",
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


# Minimum romanized-key similarity for an English/Franco spelling to be treated as
# a station-name match (tuned against the real station list — see
# scripts/test_station_translit.py).
_TRANSLIT_MATCH_THRESHOLD = 0.6


def _strip_vowels(text: str) -> str:
    return re.sub(r"[aeiou]", "", text)


def _romanized_similarity(query_key: str, name_key: str) -> float:
    """Best similarity between two romanized keys, with a vowel-stripped fallback.

    Vowels drift heavily across Franco/English spellings ("Suez" vs "Sweis"), so we
    also compare consonant skeletons and take the more forgiving score.
    """
    if not query_key or not name_key:
        return 0.0
    # Guard against generic sentences (e.g. "what are your prices") whose leftover
    # words form a key far longer than any station name — a real spelling has a
    # length comparable to the station name it represents.
    if min(len(query_key), len(name_key)) / max(len(query_key), len(name_key)) < 0.5:
        return 0.0
    direct = difflib.SequenceMatcher(None, query_key, name_key).ratio()
    skeleton = difflib.SequenceMatcher(
        None, _strip_vowels(query_key), _strip_vowels(name_key)
    ).ratio()
    return max(direct, skeleton)


def _transliteration_matches(query: str, search_terms: list[str]) -> list[Station]:
    """Match stations by romanizing both sides — the general bridge from any
    English/Franco-Arabic spelling to the Arabic station names in the DB, so we
    don't need a hand-maintained alias for every station."""
    # Build a key from the distinctive Latin word-tokens only. Terms can be whole
    # phrases that still contain stopwords ("nearest to Safaga"), so we tokenize and
    # drop generic/stopwords here too before romanizing.
    source = " ".join(t for t in search_terms if re.search(r"[a-zA-Z]", t)) or query
    clean_tokens: list[str] = []
    for tok in re.findall(r"[a-zA-Z]+", source):
        low = tok.lower()
        if len(low) < 3 or normalize_arabic(low) in _STATION_SEARCH_STOPWORDS:
            continue
        clean_tokens.append(low)
    query_key = romanized_key(" ".join(clean_tokens))
    if len(query_key) < 3:
        return []

    scored: list[tuple[float, Station]] = []
    for station in active_stations():
        score = _romanized_similarity(query_key, romanized_key(station.name))
        if score >= _TRANSLIT_MATCH_THRESHOLD:
            scored.append((score, station))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [station for _, station in scored]


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

    # Transliteration fallback: bridges English/Franco spellings ("Gesr El Suez")
    # to Arabic station names ("جسر السويس") without a per-station alias. Runs only
    # when the exact Arabic name/city tiers found nothing, and is preferred over the
    # weaker address-text match.
    translit_matches: list[Station] = []
    if not name_matches and not city_matches:
        translit_matches = _transliteration_matches(query, terms)

    stations = (name_matches or city_matches or translit_matches or addr_matches)[:limit]
    if not stations:
        return [
            "[Stations] No GoBus station matched this query. Tell the customer plainly you "
            "could not find that station/area and suggest the GoBus app or hotline {{HOTLINE}}. "
            "No station card is shown this turn."
        ]

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
        f"[Stations] Details for {names} (address, working hours, map link) are shown to the "
        "user as a card below."
    ]


# GoBus station names grouped by route destination (from the official station list).
# Used when a user clicks a destination chip to show all offices in that area.
DESTINATION_STATION_GROUPS: dict[str, list[str]] = {
    "الإسكندرية": ["سيدي جابر _ سموحة", "محرم بك", "ميامى", "الرويسات"],
    "الغردقة": ["الغردقة", "السقالة", "مكتب الأحياء", "سفاجا", "قرية الجونة", "سوما باي", "سهل حشيش", "القصير", "رأس سدر", "قرية تافيرا"],
    "شرم الشيخ": ["جوباص شرم", "الوطنية", "عرب سات - نبق"],
    "العين السخنة": ["بورتو السخنة", "جراند اوشن", "بورتو ساوث بيتش", "كانكون", "ديارا  كامب ( ماونتن فيو 1 )"],
    "بورسعيد": ["بورسعيد وسط البلد", "ميناء بورسعيد"],
    "دهب": ["دهب"],
    "مرسى علم": ["مرسى علم"],
    "مكادى": ["مكادى", "موسي كوست", "مطارما باي", "لاهاسيندا"],
    "نويبع": ["نويبع", "طابا هايتس"],
    "الساحل الشمالى": ["مراسى (الساحل الشمالى)", "مارينا 5", "مارينا 7", "مرسى مطروح", "الضبعة"],
    "الأقصر": ["الأقصر"],
}


_DESTINATION_LIST_CUES = {
    normalize_arabic(c)
    for c in (
        "destinations", "which destinations", "what destinations", "serve", "serves",
        "cities", "places", "routes", "وجهات", "الوجهات", "اماكن", "الاماكن", "مدن",
        "تخدم", "بتروح", "بتروحوا", "تروحوا", "وين", "فين",
    )
}


def _resolve_route_destination(city: str) -> str | None:
    """Map a user-facing destination label to a canonical route destination."""
    norm_city = normalize_arabic(city.strip())
    if not norm_city:
        return None
    for dest in {r.destination for r in active_routes() if r.destination}:
        norm_dest = normalize_arabic(dest)
        if norm_dest == norm_city or norm_city in norm_dest or norm_dest in norm_city:
            return dest
    return None


def _station_card(station: Station) -> dict[str, str]:
    return {
        "name": station.name,
        "address": _clean_station_address(station.description),
        "working_hours": station.working_hours or "",
        "map_url": station.map_url or "",
    }


def stations_for_destination(city: str) -> list[dict[str, str]]:
    """All active GoBus stations for a route destination (used by destination chips)."""
    canonical = _resolve_route_destination(city)
    if not canonical:
        return []

    by_name = {s.name: s for s in active_stations()}
    matched: list[Station] = []
    seen_ids: set[int] = set()

    def _add(station: Station | None) -> None:
        if station and station.id not in seen_ids:
            seen_ids.add(station.id)
            matched.append(station)

    for name in DESTINATION_STATION_GROUPS.get(canonical, []):
        _add(by_name.get(name))

    mapped = CITY_STATION_NAMES.get(canonical)
    if mapped:
        _add(by_name.get(mapped))

    norm_city = normalize_arabic(canonical)
    for area, origin in NEAREST_ORIGIN_REGION.items():
        if origin == canonical:
            norm_area = normalize_arabic(area)
            for station in active_stations():
                norm_name = normalize_arabic(station.name)
                if _term_matches(norm_area, norm_name):
                    _add(station)

    for station in active_stations():
        norm_name = normalize_arabic(station.name)
        if _term_matches(norm_city, norm_name):
            _add(station)

    ours = set(DESTINATION_STATION_GROUPS.get(canonical, []))
    others = {
        name
        for dest, names in DESTINATION_STATION_GROUPS.items()
        if dest != canonical
        for name in names
    }
    matched = [s for s in matched if s.name in ours or s.name not in others]

    matched.sort(key=lambda s: s.name)
    return [_station_card(s) for s in matched]


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


def _match_served_destination(db: Session, city: str) -> str | None:
    """Return the canonical Arabic name of the served destination that ``city``
    refers to, or ``None`` when GoBus does not list it as a destination.

    Matches across Arabic, English, and Franco-Arabic spellings by combining the
    alias expansion used for trip search with a romanized-key fallback, so e.g.
    "Sharm El Sheikh", "sharm", and "شرم الشيخ" all resolve to "شرم الشيخ".
    """
    if not city or not city.strip():
        return None
    served = _all_route_destinations(db)
    if not served:
        return None

    candidates = {city.strip(), *_expand_search_terms(city, db)}
    norm_candidates = {normalize_arabic(c) for c in candidates if c and c.strip()}
    key_candidates = {romanized_key(c) for c in candidates if c and c.strip()}
    norm_candidates.discard("")
    key_candidates.discard("")

    # 1) Exact/substring match after Arabic normalization (covers Arabic input and
    #    alias-resolved Arabic names like "شرم الشيخ").
    for dest in served:
        norm_dest = normalize_arabic(dest)
        if any(nc and (nc in norm_dest or norm_dest in nc) for nc in norm_candidates):
            return dest

    # 2) Romanized fuzzy match for English / Franco-Arabic spellings not covered by
    #    the alias maps (e.g. a destination spelled phonetically).
    best_name, best_score = None, 0.0
    for dest in served:
        dest_key = romanized_key(dest)
        for kc in key_candidates:
            score = _romanized_similarity(kc, dest_key)
            if score > best_score:
                best_name, best_score = dest, score
    if best_name and best_score >= _TRANSLIT_MATCH_THRESHOLD:
        return best_name
    return None


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
                "as chips below."
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


VALID_KB_TOPICS = frozenset({"faq", "services", "about", "policies", "destinations"})


def fetch_kb_topic_blocks(
    db: Session,
    query: str,
    topics: list[str] | None = None,
    *,
    limit: int = 10,
) -> str:
    """Build a KB context string for the ``search_knowledge_base`` tool.

    ``topics`` is a subset of {faq, services, about, policies, destinations}. The
    LLM picks them; we fetch the matching articles/services/destinations and merge
    them into one context block the model answers from. Place-name normalization
    still flows through ``_expand_search_terms`` so Arabic DB rows match.
    """
    q = (query or "").strip()
    if not q:
        return ""

    requested = [t for t in (topics or []) if t in VALID_KB_TOPICS]
    if not requested:
        requested = ["faq"]
    # Preserve a stable, sensible ordering regardless of how the LLM listed them.
    ordered = [t for t in ("destinations", "services", "faq", "about", "policies") if t in requested]

    search_terms = _expand_search_terms(q, db)
    if "stations" in ordered or "about" in ordered:
        search_terms.extend(["جوباص", "جو باص", "شركة", "مساهمة", "gobus", "about", "company"])
    if "faq" in ordered:
        search_terms.extend(["حجز", "booking", "ticket", "تذكرة"])

    groups: list[list[str]] = []
    for topic in ordered:
        if topic == "destinations":
            groups.append(_fetch_destination_blocks(db, q, search_terms))
        elif topic == "services":
            svc_blocks = _fetch_service_blocks(db, search_terms)
            bus_classes = (
                db.query(KbArticle)
                .filter(KbArticle.slug == "faq-bus-classes", KbArticle.is_active.is_(True))
                .first()
            )
            if bus_classes and not any(bus_classes.title in b for b in svc_blocks):
                svc_blocks.insert(0, f"[FAQ] {bus_classes.title}\n{bus_classes.content[:4000]}")
            groups.append(svc_blocks)
        elif topic == "faq":
            faq_blocks = _fetch_kb_category_blocks(db, "faq", search_terms, article_limit=5)
            if not any("حجز" in b or "book" in b.lower() for b in faq_blocks):
                booking = db.query(KbArticle).filter(KbArticle.slug == "faq-booking-gobus").first()
                if booking:
                    faq_blocks.insert(0, f"[FAQ] {booking.title}\n{booking.content[:4000]}")
            groups.append(faq_blocks)
        elif topic == "about":
            groups.append(_fetch_kb_category_blocks(db, "about", search_terms, article_limit=6))
        elif topic == "policies":
            groups.append(_fetch_kb_category_blocks(db, "policies", search_terms, article_limit=4))

    return _merge_context_parts(*groups, limit=limit)
