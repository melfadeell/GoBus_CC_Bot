"""Extra demo routes, KB articles, and trip seeding for presentations."""

import random
import uuid
from datetime import date, datetime, timedelta, time

from sqlalchemy.orm import Session

from app.core.constants import DASHBOARD_CHANNELS
from app.models.models import ChatMessage, ChatSession, KbArticle, KbCategory, Route, Trip

# Merged into seed — Cairo→دهب and more coastal routes
EXTRA_ROUTE_CONFIG = [
    ("القاهرة", "دهب", 480, 550, ["standard", "elite"], 4),
    ("القاهرة", "مرسى علم", 520, 600, ["standard", "elite"], 3),
    ("القاهرة", "مكادى", 400, 470, ["standard"], 3),
    ("القاهرة", "نويبع", 500, 580, ["standard"], 3),
    ("القاهرة", "الساحل الشمالى", 200, 250, ["standard", "elite"], 4),
    ("الإسكندرية", "الغردقة", 420, 500, ["standard", "elite"], 3),
    ("القاهرة", "الأقصر", 600, 680, ["standard", "elite"], 2),
]

DEMO_KB_ARTICLES = [
    (
        "faq-booking-gobus",
        "faq",
        "كيف أحجز تذكرة GoBus؟",
        """## طرق الحجز

- **الحجز أونلاين:** من موقع GoBus الرسمي — اختر الوجهة والتاريخ وعدد المقاعد وأكمل الدفع.
- **الخط الساخن:** اتصل على **19567** وسيساعدك موظف خدمة العملاء في الحجز أو الاستفسار.
- **المحطات:** يمكنك الحجز من مكاتب المحطات المعتمدة خلال مواعيد العمل.

## ملاحظات

- الحجز متاح لرحلات **GoBus** فقط في هذا النظام.
- تأكد من وجود مقاعد متاحة قبل الدفع.""",
        "gobus",
    ),
    (
        "faq-trip-schedules",
        "faq",
        "كيف أعرف مواعيد الرحلات؟",
        """## مواعيد الرحلات

- اسأل المساعد عن مسار محدد (مثل: القاهرة – دهب أو Cairo – Alexandria).
- المواعيد تشمل: تاريخ الرحلة، وقت المغادرة والوصول، الفئة، المقاعد المتاحة، والسعر.
- الرحلات المعروضة هي الرحلات القادمة من بيانات النظام التجريبية.""",
        "gobus",
    ),
    (
        "faq-hotline",
        "faq",
        "ما هو الخط الساخن؟",
        """الخط الساخن لـ GoBus هو **19567**.

يتوفر يومياً للاستفسار عن:
- الحجز والتذاكر
- مواعيد الرحلات
- المحطات والوجهات""",
        "all",
    ),
    (
        "faq-cancellation",
        "faq",
        "سياسة الإلغاء والاسترداد",
        """## الإلغاء

- يمكن إلغاء التذكرة قبل موعد الرحلة وفق سياسة الشركة.
- للتفاصيل الدقيقة والاسترداد، تواصل على الخط الساخن **19567** أو راجع الشروط والأحكام في قاعدة المعرفة.""",
        "gobus",
    ),
    (
        "faq-bus-classes",
        "faq",
        "ما الفرق بين فئات الأتوبيس؟",
        """## فئات الرحلات

- **Standard:** السعر الاقتصادي — مقاعد مريحة وتكييف.
- **Elite:** راحة أعلى ومساحة أكبر للأرجل.
- **Business:** أعلى مستوى خدمة — متوفرة على بعض المسارات (مثل القاهرة – الإسكندرية).""",
        "gobus",
    ),
]

DEPARTURE_SLOTS = [
    time(6, 0),
    time(8, 30),
    time(11, 0),
    time(14, 0),
    time(17, 30),
    time(20, 0),
    time(22, 30),
]


def _generate_trips_for_route(
    db: Session, route: Route, classes: list[str], days: int = 14, *, force: bool = False
) -> None:
    """Generate trips for a route.

    By default this is a no-op if the route already has trips. Pass force=True
    to (re)generate regardless — callers must clear existing trips first.
    """
    if not force and db.query(Trip).filter(Trip.route_id == route.id).count() > 0:
        return

    today = date.today()
    price_map = {"standard": 150, "elite": 250, "business": 350}

    for day_offset in range(days):
        trip_date = today + timedelta(days=day_offset)
        num_trips = random.randint(3, 5)
        slots = random.sample(DEPARTURE_SLOTS, min(num_trips, len(DEPARTURE_SLOTS)))
        for dep in sorted(slots):
            bus_class = random.choice(classes)
            total = random.choice([45, 49])
            # Ensure some trips have seats for demo (especially Dahab tomorrow)
            if route.destination == "دهب" and day_offset == 0 and dep == time(8, 30):
                available = random.randint(12, 30)
            else:
                available = random.randint(5, total)
            is_full = available == 0
            arr_dt = datetime.combine(trip_date, dep) + timedelta(minutes=route.duration_minutes)
            db.add(
                Trip(
                    route_id=route.id,
                    trip_date=trip_date,
                    departure_time=dep,
                    arrival_time=arr_dt.time(),
                    bus_class=bus_class,
                    total_seats=total,
                    available_seats=available,
                    price_egp=price_map.get(bus_class, 150) + random.randint(-20, 80),
                    is_bookable=not is_full,
                    status="full" if is_full else "open",
                )
            )


def ensure_extra_routes_and_trips(db: Session, base_config: list, extra_config: list | None = None) -> None:
    """Add missing routes from config lists and seed trips per route."""
    all_configs = list(base_config) + list(extra_config or EXTRA_ROUTE_CONFIG)
    for origin, destination, duration, distance, classes, _ in all_configs:
        route = (
            db.query(Route)
            .filter(Route.origin == origin, Route.destination == destination)
            .first()
        )
        if not route:
            route = Route(
                origin=origin,
                destination=destination,
                service_code="gobus",
                duration_minutes=duration,
                distance_km=distance,
            )
            db.add(route)
            db.flush()
        _generate_trips_for_route(db, route, classes)
    db.commit()


def regenerate_all_trips(db: Session, days: int = 14) -> int:
    """Delete all existing trips and regenerate a fresh window from today.

    Use this to recover when the originally seeded trip window has expired
    (all trips in the past), which makes trip queries return nothing. Bus
    classes are taken from the known route configs, defaulting to
    ["standard", "elite"] for any route not in the configs.

    Returns the number of trips created.
    """
    # Lazy import to avoid a circular import (seed_website_data imports this module).
    from app.seed.seed_website_data import ROUTE_CONFIG

    class_map = {
        (origin, destination): classes
        for origin, destination, _dur, _dist, classes, _ in list(ROUTE_CONFIG) + list(EXTRA_ROUTE_CONFIG)
    }

    db.query(Trip).delete(synchronize_session=False)
    db.flush()

    routes = db.query(Route).filter(Route.is_active.is_(True)).all()
    for route in routes:
        classes = class_map.get((route.origin, route.destination), ["standard", "elite"])
        _generate_trips_for_route(db, route, classes, days=days, force=True)

    db.commit()
    return db.query(Trip).count()


def seed_demo_kb_articles(db: Session, categories: dict[str, KbCategory]) -> None:
    for slug, cat_code, title, content, scope in DEMO_KB_ARTICLES:
        cat = categories.get(cat_code)
        if not cat:
            continue
        existing = db.query(KbArticle).filter(KbArticle.slug == slug).first()
        if existing:
            existing.title = title
            existing.content = content
            existing.category_id = cat.id
            existing.service_scope = scope
            existing.is_active = True
        else:
            db.add(
                KbArticle(
                    category_id=cat.id,
                    title=title,
                    slug=slug,
                    content=content,
                    service_scope=scope,
                    is_active=True,
                )
            )
    db.commit()


DEMO_USER_MESSAGES = [
    "فين أقرب محطة في مدينة نصر؟",
    "مواعيد رحلة القاهرة – الإسكندرية",
    "كيف أحجز تذكرة GoBus؟",
    "What is the next trip to Dahab?",
    "إيه الخط الساخن؟",
]

DEMO_ASSISTANT_SNIPPET = (
    "شكراً لتواصلك مع GoBus. يمكنني مساعدتك في المحطات، المواعيد، والحجز. "
    "للحجز أونلاين أو عبر الخط الساخن **19567**."
)


def seed_demo_analytics(db: Session) -> None:
    """Seed demo chat sessions across channels for dashboard charts."""
    if db.query(ChatSession).filter(ChatSession.session_id.like("demo-%")).count() > 0:
        return

    today = datetime.now()
    for ch in DASHBOARD_CHANNELS:
        for day_offset in range(14):
            day = today - timedelta(days=day_offset)
            sessions_today = random.randint(1, 3 if ch == "website" else 2)
            for _ in range(sessions_today):
                sid = f"demo-{ch}-{uuid.uuid4().hex[:10]}"
                started = day.replace(
                    hour=random.randint(8, 20),
                    minute=random.randint(0, 59),
                    second=0,
                    microsecond=0,
                )
                session = ChatSession(session_id=sid, channel=ch, started_at=started)
                db.add(session)
                db.flush()

                user_text = random.choice(DEMO_USER_MESSAGES)
                db.add(
                    ChatMessage(
                        session_id=sid,
                        role="user",
                        content=user_text,
                        created_at=started,
                    )
                )
                prompt_t = random.randint(180, 420)
                completion_t = random.randint(80, 260)
                db.add(
                    ChatMessage(
                        session_id=sid,
                        role="assistant",
                        content=DEMO_ASSISTANT_SNIPPET,
                        prompt_tokens=prompt_t,
                        completion_tokens=completion_t,
                        total_tokens=prompt_t + completion_t,
                        created_at=started + timedelta(seconds=random.randint(2, 30)),
                    )
                )

                if random.random() < 0.35:
                    follow_up = started + timedelta(minutes=random.randint(1, 5))
                    db.add(
                        ChatMessage(
                            session_id=sid,
                            role="user",
                            content=random.choice(DEMO_USER_MESSAGES),
                            created_at=follow_up,
                        )
                    )
                    p2 = random.randint(200, 500)
                    c2 = random.randint(100, 300)
                    db.add(
                        ChatMessage(
                            session_id=sid,
                            role="assistant",
                            content=DEMO_ASSISTANT_SNIPPET,
                            prompt_tokens=p2,
                            completion_tokens=c2,
                            total_tokens=p2 + c2,
                            created_at=follow_up + timedelta(seconds=15),
                        )
                    )

    db.commit()
