import re

# Arabic letter-form unification for fuzzy matching.
# Users frequently type alef/ya/ta-marbuta variants that differ from the
# canonical spelling stored in the DB (e.g. الاسكندرية vs الإسكندرية),
# which breaks exact SQL LIKE matching. Normalizing both sides fixes that.
_ARABIC_DIACRITICS_RE = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_ARABIC_CHAR_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ئ": "ي",
        "ؤ": "و",
        "ة": "ه",
        "گ": "ك",
        "ﻷ": "لا",
    }
)


def normalize_arabic(text: str | None) -> str:
    """Normalize Arabic text for fuzzy/substring matching.

    Removes diacritics and tatweel, unifies alef/ya/ta-marbuta/hamza forms,
    drops punctuation (e.g. trailing ؟ ، ?), lowercases latin, collapses whitespace.
    """
    if not text:
        return ""
    text = _ARABIC_DIACRITICS_RE.sub("", text)
    text = text.translate(_ARABIC_CHAR_MAP)
    # Replace punctuation with spaces so "نصر؟" matches "نصر" (keep letters/digits).
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:200] or "item"


def unique_slug(base: str, existing: set[str]) -> str:
    slug = slugify(base) or "item"
    candidate = slug
    n = 2
    while candidate in existing:
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


def clean_text_content(raw: str) -> str:
    lines = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() in {"hero", "value"}:
            continue
        lines.append(stripped)
    return "\n\n".join(lines)


def extract_working_hours(description: str) -> str | None:
    match = re.search(r"مواعيد العمل\s*:\s*(.+?)(?:\r|\n|$)", description)
    if match:
        return match.group(1).strip()
    return None


def parse_faq_pairs(content: str) -> list[tuple[str, str]]:
    blocks = re.split(r"\n\s*\n", content.strip())
    pairs: list[tuple[str, str]] = []
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) >= 2:
            pairs.append((lines[0], "\n".join(lines[1:])))
    return pairs
