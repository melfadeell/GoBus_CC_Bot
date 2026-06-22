"""LLM-based query correction run before KB retrieval.

Cleans the customer's message into a precise search query so the downstream
keyword/route matching (and the SQL it builds) runs correctly — e.g. splitting
glued Arabic prepositions like "للإسكندرية" → "إلى الإسكندرية", fixing typos,
and expanding abbreviations. Uses a small, fast model so it adds minimal latency.
"""

import logging
import re

from openai import OpenAIError
from app.services.openai_client import get_openai_client

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_TRIVIAL_RE = re.compile(r"^[\s\W\d]*$")

_SYSTEM_PROMPT = """You normalize a GoBus customer's message into a short search query for an Arabic trips/stations database.

The database stores Egyptian city, area, and station names in ARABIC. So:
- Translate English/foreign place names to the common Egyptian Arabic name, e.g. "fifth settlement" → "التجمع الخامس", "Nasr City" → "مدينة نصر", "street 90"/"90th street" → "شارع التسعين", "Rehab" → "الرحاب", "Sheikh Zayed" → "الشيخ زايد", "Alexandria"/"alex" → "الإسكندرية", "Cairo" → "القاهرة", "Hurghada" → "الغردقة", "Sharm"/"Sharm El Sheikh" → "شرم الشيخ", "Dahab" → "دهب".
- Convert Franco-Arabic (Arabic written in Latin letters/numbers) to proper Arabic, e.g. "share3 el 90" → "شارع التسعين", "el tagamo3 el khames" → "التجمع الخامس", "mafish 7aga" → "لا يوجد", "madinet nasr" → "مدينة نصر".
- Write street/road numbers as Arabic words, not digits: "street 90" / "شارع 90" → "شارع التسعين", "شارع 45" → "شارع الخامس والأربعين".
- Split glued Arabic prepositions, e.g. "للإسكندرية" → "إلى الإسكندرية", "بالقاهرة" → "القاهرة".
- Fix obvious spelling mistakes. Keep origin and destination explicit.
- Preserve qualifiers like latest/cheapest/today/tomorrow and any number of trips.
- Do NOT add places, dates, or details the user did not mention. Do NOT answer the question.
- Keep proper nouns the database needs in Arabic, but you may keep the rest of the sentence brief.

Output ONLY the rewritten query on one line — no quotes, no explanation."""


def needs_rewrite(message: str) -> bool:
    """Run the rewrite for any real message (it normalizes EN/Franco-Arabic place
    names to the Arabic the DB stores). Skip only empty/punctuation-only input."""
    return bool(message and not _TRIVIAL_RE.match(message))


async def correct_query(message: str, history_text: str | None = None) -> str:
    """Return a corrected search query, or the original on any issue."""
    msg = (message or "").strip()
    if not msg or not settings.openai_api_key or not settings.query_rewrite_enabled:
        return msg
    try:
        client = get_openai_client()
        user_content = msg
        if history_text and history_text.strip():
            user_content = f"Recent conversation (for context only): {history_text[-400:]}\n\nUser message: {msg}"
        resp = await client.chat.completions.create(
            model=settings.query_rewrite_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=60,
        )
        out = (resp.choices[0].message.content or "").strip().strip('"').strip()
        # Guard against the model returning something empty or runaway.
        if out and len(out) <= 200:
            return out
        return msg
    except OpenAIError as exc:
        logger.warning("Query rewrite failed (%s); using original", exc)
        return msg
    except Exception as exc:  # pragma: no cover - never break chat on rewrite
        logger.warning("Query rewrite error (%s); using original", exc)
        return msg
