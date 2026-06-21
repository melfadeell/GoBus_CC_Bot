"""Knowledge base retrieval helpers for chat context."""

import re
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.models import Destination, KbArticle, KbCategory, Route, Service, Station, Trip

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
    "station", "location", "map", "where", "address", "directions", "branch", "office",
    "محطة", "موقع", "فين", "عنوان", "خريطة", "مكان", "فرع", "لوكيشن",
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

    for route in db.query(Route).filter(Route.is_active.is_(True)).all():
        if route.origin in query:
            terms.append(route.origin)
        if route.destination in query:
            terms.append(route.destination)

    for station in db.query(Station).filter(Station.is_active.is_(True)).all():
        if station.name in query:
            terms.append(station.name)
        if station.city and station.city in query:
            terms.append(station.city)

    for dest in db.query(Destination).filter(Destination.is_active.is_(True)).all():
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


def _should_include_trips(query: str, search_terms: list[str]) -> bool:
    if _mentions_booking(query) and not _mentions_trips(query):
        return False
    if _mentions_trips(query):
        return True
    if _mentions_destination(query) and any(
        hint in query.lower() for hint in ("schedule", "trip", "price", "seat", "next", "مواعيد", "رحلة", "سعر", "مقعد")
    ):
        return True
    return any(
        route_hint in t
        for t in search_terms
        for route_hint in ("دهب", "الإسكندرية", "مرسى علم", "الغردقة", "شرم")
    ) and _mentions_trips(query)


def _trip_route_terms(search_terms: list[str]) -> list[str]:
    """Prefer origin/destination names over generic tokens for route matching."""
    route_terms: list[str] = []
    for term in search_terms:
        if len(term) >= 3 and term not in TRIP_KEYWORDS:
            route_terms.append(term)
    return route_terms[:6]


def _fetch_trip_blocks(db: Session, search_terms: list[str], *, limit: int = 8) -> list[str]:
    route_terms = _trip_route_terms(search_terms)
    if not route_terms:
        return []

    trip_filters = []
    for term in route_terms:
        p = _like_pattern(term)
        trip_filters.append(Route.origin.like(p))
        trip_filters.append(Route.destination.like(p))

    query = (
        db.query(Trip)
        .join(Route)
        .options(joinedload(Trip.route))
        .filter(Route.is_active.is_(True))
        .filter(Trip.trip_date >= date.today())
        .filter(Trip.status.in_(["open", "full"]))
        .filter(or_(*trip_filters))
        .order_by(Trip.trip_date, Trip.departure_time)
    )

    origin_terms = [t for t in route_terms if "قاهرة" in t or t.lower() == "cairo"]
    dest_terms = [t for t in route_terms if t not in origin_terms]
    if origin_terms and dest_terms:
        origin_filters = [Route.origin.like(_like_pattern(t)) for t in origin_terms]
        dest_filters = [Route.destination.like(_like_pattern(t)) for t in dest_terms]
        query = query.filter(or_(*origin_filters)).filter(or_(*dest_filters))

    trips = query.limit(limit).all()
    blocks: list[str] = []
    for trip in trips:
        if not trip.route:
            continue
        bookable = "متاح للحجز" if trip.is_bookable and trip.status == "open" else "غير متاح"
        blocks.append(
            f"[Trips] {trip.route.origin} → {trip.route.destination} | "
            f"التاريخ: {trip.trip_date} | المغادرة: {trip.departure_time.strftime('%H:%M')} | "
            f"الوصول: {trip.arrival_time.strftime('%H:%M')} | الفئة: {trip.bus_class} | "
            f"المقاعد المتاحة: {trip.available_seats}/{trip.total_seats} | "
            f"السعر: {trip.price_egp} جنيه | {bookable} | الحالة: {trip.status}"
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


def _fetch_station_blocks(
    db: Session,
    query: str,
    search_terms: list[str],
    *,
    limit: int = 5,
) -> list[str]:
    station_filters = []
    for term in search_terms:
        p = _like_pattern(term)
        station_filters.extend([
            Station.name.like(p),
            Station.description.like(p),
            Station.city.like(p),
        ])
    if not station_filters:
        return []

    stations = (
        db.query(Station)
        .filter(Station.is_active.is_(True))
        .filter(or_(*station_filters))
        .limit(limit if _mentions_stations(query) else 3)
        .all()
    )
    blocks: list[str] = []
    for station in stations:
        map_line = (
            f"\nMap URL (include in reply): {station.map_url}"
            if station.map_url
            else ""
        )
        hours = f"\nمواعيد العمل: {station.working_hours}" if station.working_hours else ""
        city = f"\nالمدينة: {station.city}" if station.city else ""
        blocks.append(
            f"[Stations] {station.name}{city}\n{station.description[:1200]}{hours}{map_line}"
        )
    return blocks


def _fetch_destination_blocks(
    db: Session,
    search_terms: list[str],
    *,
    limit: int = 3,
    max_chars: int = 4000,
) -> list[str]:
    dest_filters = []
    for term in search_terms:
        p = _like_pattern(term)
        dest_filters.extend([Destination.name_ar.like(p), Destination.content.like(p)])
    if not dest_filters:
        return []

    destinations = (
        db.query(Destination)
        .filter(Destination.is_active.is_(True))
        .filter(or_(*dest_filters))
        .limit(limit)
        .all()
    )
    blocks: list[str] = []
    for dest in destinations:
        blocks.append(f"[Destinations] {dest.name_ar}\n{dest.content[:max_chars]}")

    dest_cat_blocks = _fetch_kb_category_blocks(
        db, "destinations", search_terms, article_limit=2, max_chars=max_chars
    )
    blocks.extend(dest_cat_blocks)
    return blocks


def _fetch_service_blocks(db: Session, search_terms: list[str]) -> list[str]:
    blocks = _fetch_kb_category_blocks(db, "services", search_terms, article_limit=6)
    if blocks:
        return blocks

    services = db.query(Service).filter(Service.is_active.is_(True)).all()
    for svc in services:
        detail = "Full data available" if svc.has_detailed_data else "General info only"
        blocks.append(
            f"[Services] {svc.name_ar} ({svc.name_en}) - {svc.code}\n"
            f"{svc.description}\n({detail})"
        )
    return blocks


def retrieve_context(db: Session, query: str, limit: int = 10) -> str:
    q = query.strip()
    if not q:
        return ""

    search_terms = _expand_search_terms(q, db)
    intents = _detect_content_intents(q, search_terms)

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
            groups.append(_fetch_trip_blocks(db, search_terms))
        elif content_type == "stations":
            groups.append(_fetch_station_blocks(db, q, search_terms))
        elif content_type == "destinations":
            groups.append(_fetch_destination_blocks(db, search_terms))
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
