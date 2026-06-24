"""Lightweight schema migrations for existing databases."""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

OLD_ARABIC_SYSTEM_PROMPT = """أنت مساعد خدمة عملاء شركة GoBus (جوباص).
- أجب بلغة المستخدم (عربي، إنجليزي، أو أي لغة أخرى).
- استخدم فقط المعلومات من سياق قاعدة المعرفة أدناه. لا تخترع معلومات.
- البيانات التفصيلية (محطات، رحلات، وجهات، أسعار، مقاعد) متوفرة لخدمة GoBus فقط.
- لخدمتي GoMini (جوميني) و GoLemo (جوليمو): يمكنك شرح أنها خدمات نقل تابعة للمجموعة، لكن إذا سُئلت عن تفاصيل (مواعيد، محطات، حجز) قل: "لا تتوفر لدي معلومات تفصيلية عن هذه الخدمة حالياً."
- الخط الساخن: 19567 — اذكره عند طلب التواصل أو المساعدة.
- كن مهذباً، مختصراً، ومفيداً."""


def _column_exists(engine: Engine, table: str, column: str) -> bool:
    insp = inspect(engine)
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(engine: Engine, table: str, index: str) -> bool:
    insp = inspect(engine)
    try:
        return index in {ix["name"] for ix in insp.get_indexes(table)}
    except Exception:
        return False


# Indexes on hot, frequently-filtered columns (added idempotently).
_INDEXES: list[tuple[str, str, str]] = [
    ("chat_messages", "ix_chat_messages_session_created", "(session_id, created_at)"),
    ("trips", "ix_trips_route_date_status", "(route_id, trip_date, status)"),
    ("routes", "ix_routes_is_active", "(is_active)"),
    ("stations", "ix_stations_is_active", "(is_active)"),
    ("destinations", "ix_destinations_is_active", "(is_active)"),
    ("services", "ix_services_is_active", "(is_active)"),
    ("tickets", "ix_tickets_customer", "(customer_id)"),
    ("tickets", "ix_tickets_status", "(status)"),
    ("tickets", "ix_tickets_created", "(created_at)"),
    ("ticket_messages", "ix_ticket_messages_ticket", "(ticket_id, created_at)"),
    ("email_otps", "ix_email_otps_email_purpose", "(email, purpose)"),
]


def _migrate_indexes(engine: Engine) -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, name, cols in _INDEXES:
            if table not in existing_tables or _index_exists(engine, table, name):
                continue
            try:
                conn.execute(text(f"CREATE INDEX {name} ON {table} {cols}"))
                logger.info("Created index %s on %s", name, table)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not create index %s on %s: %s", name, table, exc)


def run_migrations(engine: Engine) -> None:
    # Add NEW columns the ORM models reference BEFORE any data migration runs an ORM
    # query against those tables (otherwise SELECT * fails on the missing column).
    _migrate_trip_stations(engine)

    with engine.begin() as conn:
        if not _column_exists(engine, "stations", "is_24_hours"):
            conn.execute(text("ALTER TABLE stations ADD COLUMN is_24_hours TINYINT(1) NOT NULL DEFAULT 0"))
            logger.info("Added stations.is_24_hours")
        if not _column_exists(engine, "stations", "opens_at"):
            conn.execute(text("ALTER TABLE stations ADD COLUMN opens_at VARCHAR(20) NULL"))
            logger.info("Added stations.opens_at")
        if not _column_exists(engine, "stations", "closes_at"):
            conn.execute(text("ALTER TABLE stations ADD COLUMN closes_at VARCHAR(20) NULL"))
            logger.info("Added stations.closes_at")

        # Widen service_scope
        try:
            conn.execute(text("ALTER TABLE kb_articles MODIFY COLUMN service_scope VARCHAR(50) NOT NULL DEFAULT 'gobus'"))
            logger.info("Ensured kb_articles.service_scope is VARCHAR(50)")
        except Exception:
            pass

    _migrate_kb_categories(engine)
    _migrate_services_to_kb(engine)
    _migrate_demo_data(engine)
    _migrate_prompt_default(engine)
    _migrate_general_inquiry_prompt(engine)
    _migrate_chat_image_url(engine)
    _migrate_chat_tokens_and_channels(engine)
    _migrate_prompt_hotline_placeholder(engine)
    _migrate_station_hours(engine)
    _migrate_drop_station_city(engine)
    _migrate_backfill_trip_stations(engine)
    _migrate_assign_trip_stations_by_city(engine)
    _migrate_purge_demo_sessions(engine)
    _migrate_indexes(engine)


def _migrate_station_hours(engine: Engine) -> None:
    """Pull working hours out of free-text station descriptions into the structured
    is_24_hours/opens_at/closes_at fields, then strip the 'مواعيد العمل …' segment.
    Idempotent: once stripped, the marker is gone so re-runs are no-ops."""
    from app.database import SessionLocal
    from app.models.models import Station
    from app.utils.text_utils import extract_working_hours, parse_station_hours

    db = SessionLocal()
    try:
        stations = db.query(Station).filter(Station.description.like("%مواعيد العمل%")).all()
        for s in stations:
            hours = extract_working_hours(s.description or "")
            if hours:
                is24, opens, closes = parse_station_hours(hours)
                if is24 and not s.is_24_hours:
                    s.is_24_hours = True
                if opens and not s.opens_at:
                    s.opens_at = opens
                if closes and not s.closes_at:
                    s.closes_at = closes
                if (is24 or (opens and closes)) and not s.working_hours:
                    s.working_hours = "24 hours" if is24 else f"{opens} – {closes}"
            # Strip the hours segment from the description regardless of parse success.
            import re as _re

            s.description = _re.sub(
                r"\s*مواعيد العمل\s*:[^\n]*", "", s.description or ""
            ).strip()
        db.commit()
        if stations:
            logger.info("Migrated working hours for %d stations", len(stations))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Station hours migration skipped: %s", exc)
        db.rollback()
    finally:
        db.close()


def _migrate_drop_station_city(engine: Engine) -> None:
    if _column_exists(engine, "stations", "city"):
        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE stations DROP COLUMN city"))
            logger.info("Dropped stations.city")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not drop stations.city: %s", exc)


def _migrate_trip_stations(engine: Engine) -> None:
    with engine.begin() as conn:
        for col in ("departure_station_id", "arrival_station_id"):
            if not _column_exists(engine, "trips", col):
                conn.execute(text(f"ALTER TABLE trips ADD COLUMN {col} INT NULL"))
                logger.info("Added trips.%s", col)


def _migrate_backfill_trip_stations(engine: Engine) -> None:
    """Best-effort assign departure/arrival stations to existing trips by matching
    the route origin/destination to a station name. Only fills trips where the
    station is still null, so it's safe to re-run and never overwrites admin edits."""
    from app.database import SessionLocal
    from app.models.models import Route, Station, Trip
    from app.utils.text_utils import normalize_arabic

    db = SessionLocal()
    try:
        if db.query(Trip).filter(Trip.departure_station_id.is_(None)).count() == 0:
            return
        stations = db.query(Station).filter(Station.is_active.is_(True)).all()
        norm_stations = [(s, normalize_arabic(s.name)) for s in stations]

        def match(city: str):
            norm = normalize_arabic(city)
            if not norm:
                return None
            for s, ns in norm_stations:
                if norm in ns:
                    return s
            for s, ns in norm_stations:
                if ns and ns in norm:
                    return s
            return None

        route_map = {}
        for r in db.query(Route).all():
            dep = match(r.origin)
            arr = match(r.destination)
            route_map[r.id] = (dep.id if dep else None, arr.id if arr else None)

        updated = 0
        for trip in db.query(Trip).filter(Trip.departure_station_id.is_(None)).all():
            dep_id, arr_id = route_map.get(trip.route_id, (None, None))
            if dep_id or arr_id:
                trip.departure_station_id = dep_id
                trip.arrival_station_id = arr_id
                updated += 1
        db.commit()
        if updated:
            logger.info("Backfilled stations for %d existing trips", updated)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Trip-station backfill skipped: %s", exc)
        db.rollback()
    finally:
        db.close()


def _migrate_prompt_hotline_placeholder(engine: Engine) -> None:
    """Replace the hardcoded hotline in the stored bot prompt with the {{HOTLINE}}
    placeholder, so the live hotline flows from the editable BotSettings.hotline."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE bot_settings SET system_prompt = "
                    "REPLACE(system_prompt, '19567', '{{HOTLINE}}') "
                    "WHERE system_prompt LIKE '%19567%'"
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Prompt hotline-placeholder migration skipped: %s", exc)


def _migrate_assign_trip_stations_by_city(engine: Engine) -> None:
    """Fill any still-null trip departure/arrival stations from the explicit
    city→station map, so the trip table is never blank. Fills nulls only — never
    overwrites a station already set (e.g. by an admin)."""
    from app.core.constants import CITY_STATION_NAMES
    from app.database import SessionLocal
    from app.models.models import Route, Station, Trip

    db = SessionLocal()
    try:
        name_to_id = {
            s.name: s.id
            for s in db.query(Station).filter(Station.name.in_(set(CITY_STATION_NAMES.values()))).all()
        }
        route_map: dict[int, tuple[int | None, int | None]] = {}
        for r in db.query(Route).all():
            dep = name_to_id.get(CITY_STATION_NAMES.get(r.origin, ""))
            arr = name_to_id.get(CITY_STATION_NAMES.get(r.destination, ""))
            route_map[r.id] = (dep, arr)

        updated = 0
        for trip in db.query(Trip).filter(
            (Trip.departure_station_id.is_(None)) | (Trip.arrival_station_id.is_(None))
        ).all():
            dep, arr = route_map.get(trip.route_id, (None, None))
            changed = False
            if trip.departure_station_id is None and dep is not None:
                trip.departure_station_id = dep
                changed = True
            if trip.arrival_station_id is None and arr is not None:
                trip.arrival_station_id = arr
                changed = True
            if changed:
                updated += 1
        db.commit()
        if updated:
            logger.info("Assigned city stations to %d trips", updated)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Trip city-station assignment skipped: %s", exc)
        db.rollback()
    finally:
        db.close()


def _migrate_purge_demo_sessions(engine: Engine) -> None:
    """Remove seeded demo analytics so the dashboard reflects only real usage."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM chat_messages WHERE session_id LIKE 'demo-%' "
                    "OR session_id LIKE 'demo_%'"
                )
            )
            conn.execute(
                text(
                    "DELETE FROM chat_sessions WHERE session_id LIKE 'demo-%' "
                    "OR session_id LIKE 'demo_%'"
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Demo-session purge skipped: %s", exc)


def _migrate_chat_tokens_and_channels(engine: Engine) -> None:
    with engine.begin() as conn:
        for col, ddl in [
            ("prompt_tokens", "ALTER TABLE chat_messages ADD COLUMN prompt_tokens INT NOT NULL DEFAULT 0"),
            ("completion_tokens", "ALTER TABLE chat_messages ADD COLUMN completion_tokens INT NOT NULL DEFAULT 0"),
            ("total_tokens", "ALTER TABLE chat_messages ADD COLUMN total_tokens INT NOT NULL DEFAULT 0"),
        ]:
            if not _column_exists(engine, "chat_messages", col):
                conn.execute(text(ddl))
                logger.info("Added chat_messages.%s", col)

        try:
            conn.execute(text("UPDATE chat_sessions SET channel = 'website' WHERE channel = 'web'"))
        except Exception:
            pass
    # Note: demo analytics seeding was removed — the dashboard now shows only real
    # usage. _migrate_purge_demo_sessions clears any previously seeded demo data.


def _migrate_kb_categories(engine: Engine) -> None:
    from app.database import SessionLocal
    from app.models.models import KbArticle, KbCategory

    db = SessionLocal()
    try:
        cats = {c.code: c for c in db.query(KbCategory).all()}
        contact = cats.get("contact")
        about = cats.get("about")
        general = cats.get("general")
        faq = cats.get("faq")

        if contact and about:
            updated = (
                db.query(KbArticle)
                .filter(KbArticle.category_id == contact.id)
                .update({KbArticle.category_id: about.id}, synchronize_session=False)
            )
            if updated:
                logger.info("Reassigned %d contact articles to about", updated)

        if general and faq:
            updated = (
                db.query(KbArticle)
                .filter(KbArticle.category_id == general.id)
                .update({KbArticle.category_id: faq.id}, synchronize_session=False)
            )
            if updated:
                logger.info("Reassigned %d general articles to faq", updated)

        db.commit()
    finally:
        db.close()


def _migrate_services_to_kb(engine: Engine) -> None:
    from app.database import SessionLocal
    from app.seed.seed_website_data import ensure_categories, seed_services, seed_services_kb_articles

    db = SessionLocal()
    try:
        categories = ensure_categories(db)
        seed_services(db)
        seed_services_kb_articles(db, categories)
    finally:
        db.close()


def _migrate_demo_data(engine: Engine) -> None:
    from app.database import SessionLocal
    from app.seed.seed_demo_data import EXTRA_ROUTE_CONFIG, ensure_extra_routes_and_trips, seed_demo_kb_articles
    from app.seed.seed_website_data import ROUTE_CONFIG, ensure_categories

    db = SessionLocal()
    try:
        categories = ensure_categories(db)
        ensure_extra_routes_and_trips(db, ROUTE_CONFIG, EXTRA_ROUTE_CONFIG)
        seed_demo_kb_articles(db, categories)
    finally:
        db.close()


def _migrate_chat_image_url(engine: Engine) -> None:
    with engine.begin() as conn:
        if not _column_exists(engine, "chat_messages", "image_url"):
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN image_url VARCHAR(500) NULL"))
            logger.info("Added chat_messages.image_url")


def _migrate_general_inquiry_prompt(engine: Engine) -> None:
    from app.core.constants import DEFAULT_SYSTEM_PROMPT
    from app.database import SessionLocal
    from app.models.models import BotSettings
    from app.seed.seed_website_data import ensure_categories, ensure_company_overview_article

    marker = "**Do not** mention the hotline in every reply"
    db = SessionLocal()
    try:
        categories = ensure_categories(db)
        ensure_company_overview_article(db, categories)

        bot = db.query(BotSettings).first()
        if bot and marker not in bot.system_prompt:
            bot.system_prompt = DEFAULT_SYSTEM_PROMPT
            db.commit()
            logger.info("Updated bot prompt (stations, hotline, app issues)")
    finally:
        db.close()


def _migrate_prompt_default(engine: Engine) -> None:
    from app.core.constants import DEFAULT_SYSTEM_PROMPT
    from app.database import SessionLocal
    from app.models.models import BotPromptVersion, BotSettings

    db = SessionLocal()
    try:
        bot = db.query(BotSettings).first()
        if not bot:
            return
        if bot.system_prompt.strip() == OLD_ARABIC_SYSTEM_PROMPT.strip():
            bot.system_prompt = DEFAULT_SYSTEM_PROMPT
            db.commit()
            logger.info("Migrated bot system_prompt to English default")

        if db.query(BotPromptVersion).count() == 0:
            db.add(
                BotPromptVersion(
                    version_number=1,
                    system_prompt=bot.system_prompt,
                    instruction_note="Initial prompt",
                    created_by=None,
                )
            )
            db.commit()
            logger.info("Created initial prompt version")
    finally:
        db.close()
