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
    _migrate_indexes(engine)


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

    from app.database import SessionLocal
    from app.seed.seed_demo_data import seed_demo_analytics

    db = SessionLocal()
    try:
        seed_demo_analytics(db)
    finally:
        db.close()


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
