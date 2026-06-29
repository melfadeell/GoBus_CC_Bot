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


# Arabic letter → Latin (Egyptian-style) romanization for matching English /
# Franco-Arabic spellings of place names against the Arabic names stored in the DB
# (e.g. "Gesr El Suez" ↔ "جسر السويس"). This is deliberately phonetic, not a
# scholarly transliteration — it only needs to be close enough for fuzzy matching.
_ARABIC_ROMAN_MAP = {
    "ء": "", "ٱ": "a", "آ": "a", "أ": "a", "إ": "a", "ا": "a",
    "ب": "b", "ت": "t", "ة": "a", "ث": "s", "ج": "g", "ح": "h",
    "خ": "kh", "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s",
    "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a",
    "غ": "gh", "ف": "f", "ق": "k", "ك": "k", "ل": "l", "م": "m",
    "ن": "n", "ه": "h", "و": "w", "ي": "y", "ى": "a", "ئ": "y", "ؤ": "w",
    "ـ": "",
}
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def romanize_arabic(text: str | None) -> str:
    """Transliterate Arabic text to a lowercase Latin approximation.

    Latin characters already present pass through unchanged. The result is meant
    for fuzzy comparison (see ``romanized_key``), not for display.
    """
    if not text:
        return ""
    text = _ARABIC_DIACRITICS_RE.sub("", text)
    text = text.translate(_ARABIC_DIGITS)
    out: list[str] = []
    for ch in text:
        if ch in _ARABIC_ROMAN_MAP:
            out.append(_ARABIC_ROMAN_MAP[ch])
        elif ch.isalnum():
            out.append(ch.lower())
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


# Articles/fillers that appear detached in English ("El Suez") but glued in the
# Arabic romanization ("alswys"); dropping them aligns the two spellings.
_ROMAN_FILLER_TOKENS = {"el", "al", "the", "a", "an", "of"}


def romanized_key(text: str | None) -> str:
    """A compact, article-free key from (possibly Arabic) text for fuzzy matching.

    Romanizes, splits to tokens, strips definite articles (detached *and* the
    glued ``al-`` prefix), and concatenates — so "Gesr El Suez" and the
    romanized "gsr alswys" both reduce to comparable keys.
    """
    roman = romanize_arabic(text)
    tokens: list[str] = []
    seen: set[str] = set()
    for tok in re.findall(r"[a-z0-9]+", roman):
        if tok in _ROMAN_FILLER_TOKENS:
            continue
        if tok.startswith("al") and len(tok) > 4:
            tok = tok[2:]
        # De-dup: callers often pass overlapping terms (a full phrase plus its
        # individual words), which would otherwise inflate the key and skew scores.
        if tok in seen:
            continue
        seen.add(tok)
        tokens.append(tok)
    return "".join(tokens)


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


_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _to_12h(hour24: int) -> str:
    """Format an hour (0-23) as the 12-hour 'h:00 AM/PM' string the station UI uses
    (see frontend TIME_OPTIONS in utils/stationHours.ts)."""
    hour24 %= 24
    period = "AM" if hour24 < 12 else "PM"
    h = hour24 % 12 or 12
    return f"{h}:00 {period}"


def _parse_one_time(seg: str) -> str | None:
    seg = seg.translate(_AR_DIGITS)
    if "منتصف الليل" in seg:  # midnight / after-midnight → 12 AM
        return "12:00 AM"
    m = re.search(r"(\d{1,2})(?::(\d{2}))?", seg)
    if not m:
        return None
    hour = int(m.group(1))
    has_colon = m.group(2) is not None
    # 24-hour numeric (e.g. "23:00") — derive AM/PM from the value itself.
    if hour >= 13 or (has_colon and hour == 0):
        return _to_12h(hour)
    if "مساء" in seg or "ظهر" in seg:  # PM
        return _to_12h(hour % 12 + 12)
    if "صباح" in seg or "فجر" in seg:  # AM (12 صباحاً → midnight)
        return _to_12h(hour % 12)
    return _to_12h(hour % 24)


def parse_station_hours(text: str | None) -> tuple[bool, str | None, str | None]:
    """Parse an Arabic working-hours phrase into (is_24_hours, opens_at, closes_at).

    Handles "24 ساعة" and ranges like "من 8 صباحاً إلي 11 مساءً" /
    "من 8:00 صباحاً إلي 23:00 مساءً" / "... إلي 12 بعد منتصف الليل". The opens/closes
    strings match the frontend TIME_OPTIONS values ("8:00 AM", "11:00 PM")."""
    if not text:
        return (False, None, None)
    if "24" in text and "ساع" in text:
        return (True, None, None)
    parts = [p.strip() for p in re.split(r"إل[يى]|ال[يى]|حتى|–|—|-", text) if p.strip()]
    if parts and parts[0].startswith("من"):
        parts[0] = parts[0][2:].strip()
    if len(parts) >= 2:
        opens = _parse_one_time(parts[0])
        closes = _parse_one_time(parts[1])
        if opens and closes:
            return (False, opens, closes)
    return (False, None, None)


def parse_faq_pairs(content: str) -> list[tuple[str, str]]:
    blocks = re.split(r"\n\s*\n", content.strip())
    pairs: list[tuple[str, str]] = []
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) >= 2:
            pairs.append((lines[0], "\n".join(lines[1:])))
    return pairs
