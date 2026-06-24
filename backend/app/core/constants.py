"""Shared application constants."""

from pathlib import Path

from app.config import get_settings

# The bot system prompt lives in a text file (single source of truth). It seeds the
# DB bot_settings row on first run; thereafter the DB row is the live, editable copy.
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "system_prompt.txt"
DEFAULT_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").strip()

DEFAULT_GREETING_AR = "مرحباً! أنا مساعد جوباص. كيف يمكنني مساعدتك اليوم؟"
DEFAULT_HOTLINE = "19567"

CHAT_ERROR_MESSAGE = "عذراً، حدث خطأ أثناء معالجة رسالتك. يرجى المحاولة مرة أخرى لاحقاً."

CHAT_CHANNELS = (
    "whatsapp",
    "instagram",
    "linkedin",
    "facebook",
    "tiktok",
    "website",
)

# Dashboard reflects only real channels (seeded demo analytics were removed).
DASHBOARD_CHANNELS = CHAT_CHANNELS

DEFAULT_CHAT_CHANNEL = "website"

# --- CRM / ticketing ---
TICKET_CATEGORIES = (
    "booking",
    "refund_payment",
    "complaint",
    "lost_item",
    "schedule_trip",
    "other",
)
TICKET_STATUSES = (
    "open",
    "in_progress",
    "waiting_customer",
    "resolved",
    "closed",
)
TICKET_PRIORITIES = ("low", "medium", "high", "urgent")
DEFAULT_TICKET_PRIORITY = "medium"

# Representative station (by exact name) for each route origin/destination city.
# The canonical map lives in Settings (env-overridable via CITY_STATION_NAMES);
# this alias keeps existing imports working and reflects any override.
CITY_STATION_NAMES: dict[str, str] = get_settings().city_station_names

def estimate_cost_usd(model: str | None, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for a model's input/output token counts.

    Pricing (USD per 1M tokens) comes from Settings.model_pricing, which is
    env-overridable via the MODEL_PRICING env var — no code change needed."""
    settings = get_settings()
    rate = settings.model_pricing.get(model or "", settings.default_model_pricing)
    in_rate, out_rate = rate[0], rate[1]
    return (prompt_tokens / 1_000_000) * in_rate + (completion_tokens / 1_000_000) * out_rate
