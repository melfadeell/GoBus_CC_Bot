import json
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import get_settings
from app.database import SessionLocal
from app.models.models import (
    AdminUser,
    BotSettings,
    Destination,
    KbArticle,
    KbCategory,
    Route,
    Service,
    Station,
    Trip,
)
from app.core.constants import DEFAULT_GREETING_AR, DEFAULT_HOTLINE, DEFAULT_SYSTEM_PROMPT
from app.seed.seed_demo_data import (
    EXTRA_ROUTE_CONFIG,
    ensure_extra_routes_and_trips,
    seed_demo_kb_articles,
)
from app.utils.text_utils import (
    clean_text_content,
    extract_working_hours,
    parse_faq_pairs,
    slugify,
)

settings = get_settings()

CATEGORY_MAP = {
    "معلومات عنا.txt": ("about", "معلومات عنا"),
    "أسئلة شائعة.txt": ("faq", "أسئلة شائعة"),
    "الشروط والأحكام.txt": ("policies", "الشروط والأحكام"),
    "سياسة الخصوصية لموقع جو باص.txt": ("policies", "سياسة الخصوصية"),
    "إتصل بنا.txt": ("contact", "اتصل بنا"),
}

DESTINATION_WEB_IDS = {
    "مدينة بور سعيد": 35,
    "مدينة الغردقة": 1,
    "مدينة الساحل الشمالى": 15,
    "مدينة شرم الشيخ": 3,
    "مدينة الاسكندرية": 4,
    "مدينة العين السخنة": 11,
    "مدينة دهب": 23,
    "مدينة مكادى": 18,
    "مدينة مرسي علم": 10,
    "مدينة نويبع": 29,
}

ROUTE_CONFIG = [
    ("القاهرة", "الإسكندرية", 180, 220, ["standard", "elite", "business"], 6),
    ("القاهرة", "الغردقة", 360, 450, ["standard", "elite"], 5),
    ("القاهرة", "شرم الشيخ", 420, 500, ["standard", "elite"], 4),
    ("القاهرة", "العين السخنة", 90, 120, ["standard"], 4),
    ("القاهرة", "بورسعيد", 150, 180, ["standard"], 3),
]


COMPANY_OVERVIEW_SLUG = "about-company-overview"

COMPANY_OVERVIEW_CONTENT = """## عن شركة GoBus (جو باص) — معلومات عامة

- **الشكل القانوني / الملكية:** شركة مساهمة مصرية (Egyptian joint stock company).
- **العلامات التجارية:** جو، جو ميني (GoMini)، جوليمو (GoLemo).
- **مجال العمل:** نقل الركاب بمختلف وسائل النقل داخل مصر.
- **تاريخ النشاط:** تعمل في مجال النقل منذ عام 1998.
- **إنجاز:** أول شركة قطاع خاص تعمل في مجال النقل العام للركاب تحت إشراف وزارة النقل في مصر.
- **الفروع:** شبكة فروع منتشرة في مصر (أكثر من 40 فرعاً).
- **الخط الساخن:** 19567

## Ownership / About GoBus (English)

- GoBus (جو باص) is an **Egyptian joint stock company** — a corporate entity, not a single named individual owner in public company information.
- Brands under the group include **GoBus**, **GoMini**, and **GoLemo**.
- Passenger transport across Egypt since **1998**.
- The first private-sector company licensed for public passenger transport under Egypt's Ministry of Transport.
- For specific shareholder, executive, or legal ownership details not listed here, contact hotline **19567**.

## رؤية ومهمة الشركة (ملخص)

- **الرؤية:** تقديم خدمات نقل مميزة وآمنة تتجاوز توقعات العملاء باستخدام التكنولوجيا الحديثة.
- **المهمة:** توفير خدمات نقل مريحة وموثوقة مع التركيز على راحة ورفاهية العملاء.
"""


def ensure_company_overview_article(db: Session, categories: dict[str, KbCategory]) -> None:
    """Upsert a concise company/ownership article for general inquiries."""
    about_cat = categories.get("about")
    if not about_cat:
        return

    article = db.query(KbArticle).filter(KbArticle.slug == COMPANY_OVERVIEW_SLUG).first()
    if article:
        article.title = "معلومات عامة عن شركة GoBus والملكية"
        article.content = COMPANY_OVERVIEW_CONTENT
        article.category_id = about_cat.id
        article.service_scope = "all"
        article.is_active = True
    else:
        db.add(
            KbArticle(
                category_id=about_cat.id,
                title="معلومات عامة عن شركة GoBus والملكية",
                slug=COMPANY_OVERVIEW_SLUG,
                content=COMPANY_OVERVIEW_CONTENT,
                service_scope="all",
                is_active=True,
            )
        )
    db.commit()


def ensure_categories(db: Session) -> dict[str, KbCategory]:
    codes = [
        ("services", "الخدمات"),
        ("faq", "أسئلة شائعة"),
        ("about", "معلومات عنا"),
        ("policies", "سياسات"),
        ("destinations", "الوجهات"),
        ("contact", "اتصل بنا"),
        ("general", "عام"),
    ]
    result = {}
    for code, name_ar in codes:
        cat = db.query(KbCategory).filter(KbCategory.code == code).first()
        if not cat:
            cat = KbCategory(code=code, name_ar=name_ar)
            db.add(cat)
            db.flush()
        result[code] = cat
    db.commit()
    return result


def seed_admin(db: Session) -> None:
    if not db.query(AdminUser).filter(AdminUser.email == settings.admin_email).first():
        db.add(
            AdminUser(
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
            )
        )
        db.commit()


def seed_bot_settings(db: Session) -> None:
    if not db.query(BotSettings).first():
        db.add(
            BotSettings(
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                greeting_ar=DEFAULT_GREETING_AR,
                hotline=DEFAULT_HOTLINE,
                model_name=settings.openai_model,
            )
        )
        db.commit()


def seed_services(db: Session) -> None:
    services = [
        (
            "gobus",
            "جوباص",
            "GoBus",
            "خدمة نقل الركاب بالأتوبيس المكيفة على مستوى الجمهورية. "
            "تشمل محطات متعددة، رحلات يومية، وحجز أونلاين. البيانات التفصيلية متوفرة في النظام.",
            True,
        ),
        (
            "gomini",
            "جوميني",
            "GoMini",
            "خدمة نقل مصغرة تابعة لمجموعة جو. "
            "تُستخدم في بعض المحطات والوجهات. معلومات تفصيلية غير متوفرة في هذا النظام حالياً.",
            False,
        ),
        (
            "golemo",
            "جوليمو",
            "GoLemo",
            "خدمة نقل تابعة لمجموعة جو. "
            "معلومات تفصيلية عن المواعيد والحجز غير متوفرة في هذا النظام حالياً.",
            False,
        ),
    ]
    for code, name_ar, name_en, desc, detailed in services:
        svc = db.query(Service).filter(Service.code == code).first()
        if not svc:
            db.add(
                Service(
                    code=code,
                    name_ar=name_ar,
                    name_en=name_en,
                    description=desc,
                    has_detailed_data=detailed,
                )
            )
    db.commit()


def seed_services_kb_articles(db: Session, categories: dict[str, KbCategory]) -> None:
    """Sync services table into KB articles (Services tab)."""
    services_cat = categories.get("services")
    if not services_cat:
        return

    for svc in db.query(Service).all():
        slug = f"service-{svc.code}"
        existing = db.query(KbArticle).filter(KbArticle.slug == slug).first()
        detail = "بيانات تفصيلية متوفرة" if svc.has_detailed_data else "معلومات عامة فقط"
        content = f"{svc.description}\n\n({detail})"
        if existing:
            existing.title = f"{svc.name_ar} ({svc.name_en})"
            existing.content = content
            existing.service_scope = svc.code
            existing.is_active = svc.is_active
            existing.category_id = services_cat.id
        else:
            db.add(
                KbArticle(
                    category_id=services_cat.id,
                    title=f"{svc.name_ar} ({svc.name_en})",
                    slug=slug,
                    content=content,
                    service_scope=svc.code,
                    is_active=svc.is_active,
                )
            )
    db.commit()


def import_about_files(db: Session, categories: dict[str, KbCategory], data_path: Path) -> None:
    about_dir = data_path / "about"
    if not about_dir.exists():
        return

    for file_path in about_dir.glob("*.txt"):
        raw = file_path.read_text(encoding="utf-8")
        filename = file_path.name
        cat_code, default_title = CATEGORY_MAP.get(filename, ("general", filename))

        if filename == "أسئلة شائعة.txt":
            pairs = parse_faq_pairs(raw)
            for i, (question, answer) in enumerate(pairs):
                slug = slugify(f"faq-{i}-{question[:30]}")
                if db.query(KbArticle).filter(KbArticle.slug == slug).first():
                    continue
                db.add(
                    KbArticle(
                        category_id=categories[cat_code].id,
                        title=question,
                        slug=slug,
                        content=answer,
                        service_scope="gobus",
                        source_file=str(file_path),
                    )
                )
        else:
            content = clean_text_content(raw)
            title = default_title
            slug = slugify(title)
            if db.query(KbArticle).filter(KbArticle.slug == slug).first():
                continue
            db.add(
                KbArticle(
                    category_id=categories[cat_code].id,
                    title=title,
                    slug=slug,
                    content=content,
                    service_scope="all" if cat_code == "contact" else "gobus",
                    source_file=str(file_path),
                )
            )
    db.commit()


def import_destinations(db: Session, categories: dict[str, KbCategory], data_path: Path) -> None:
    dest_dir = data_path / "destinations and there general info"
    if not dest_dir.exists():
        return

    for file_path in dest_dir.glob("*.txt"):
        raw = file_path.read_text(encoding="utf-8")
        name = file_path.stem
        content = clean_text_content(raw)
        slug = slugify(name)
        web_id = DESTINATION_WEB_IDS.get(name)

        if not db.query(Destination).filter(Destination.slug == slug).first():
            db.add(
                Destination(
                    name_ar=name,
                    slug=slug,
                    content=content,
                    gobus_web_id=web_id,
                )
            )

        kb_slug = slugify(f"dest-{name}")
        if not db.query(KbArticle).filter(KbArticle.slug == kb_slug).first():
            db.add(
                KbArticle(
                    category_id=categories["destinations"].id,
                    title=name,
                    slug=kb_slug,
                    content=content,
                    service_scope="gobus",
                    source_file=str(file_path),
                )
            )
    db.commit()


def import_stations(db: Session, data_path: Path) -> None:
    stations_file = data_path / "محطات وموانئ جوباص.json"
    if not stations_file.exists():
        return

    stations = json.loads(stations_file.read_text(encoding="utf-8"))
    for item in stations:
        name = item.get("name", "").strip()
        if not name:
            continue
        if db.query(Station).filter(Station.name == name).first():
            continue
        desc = item.get("description", "").replace("\r\n", "\n").strip()
        db.add(
            Station(
                name=name,
                description=desc,
                working_hours=extract_working_hours(desc),
                map_url=item.get("map_url"),
                map_text=item.get("map_text"),
            )
        )
    db.commit()


def seed_routes_and_trips(db: Session) -> None:
    ensure_extra_routes_and_trips(db, ROUTE_CONFIG, EXTRA_ROUTE_CONFIG)


def seed_initial_data(db: Session) -> None:
    """Load website data, services, admin, and dummy trips into an empty database."""
    data_path = Path(settings.website_data_path)
    if not data_path.is_absolute():
        data_path = Path(__file__).resolve().parents[2] / settings.website_data_path

    categories = ensure_categories(db)
    seed_admin(db)
    seed_bot_settings(db)
    seed_services(db)
    seed_services_kb_articles(db, categories)
    import_about_files(db, categories, data_path)
    ensure_company_overview_article(db, categories)
    import_destinations(db, categories, data_path)
    import_stations(db, data_path)
    seed_routes_and_trips(db)
    seed_demo_kb_articles(db, categories)


def run_seed() -> None:
    """CLI entry: ensure DB exists, create tables, seed if empty."""
    from app.core.bootstrap import bootstrap_database

    bootstrap_database()


if __name__ == "__main__":
    run_seed()
