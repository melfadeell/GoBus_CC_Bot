import re


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
