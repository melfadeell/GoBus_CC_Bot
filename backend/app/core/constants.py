"""Shared application constants."""

from pathlib import Path

# The bot system prompt lives in a text file (single source of truth). It seeds the
# DB bot_settings row on first run; thereafter the DB row is the live, editable copy.
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "system_prompt.txt"
DEFAULT_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").strip()

DEFAULT_GREETING_AR = "مرحباً! أنا مساعد جوباص. كيف يمكنني مساعدتك اليوم؟"
DEFAULT_HOTLINE = "19567"

CHAT_ERROR_MESSAGE = "عذراً، حدث خطأ أثناء معالجة رسالتك. يرجى المحاولة مرة أخرى أو الاتصال على 19567."

CHAT_CHANNELS = (
    "whatsapp",
    "instagram",
    "linkedin",
    "facebook",
    "tiktok",
    "website",
)

# Includes poc for dashboard analytics on seeded demo data
DASHBOARD_CHANNELS = ("poc",) + CHAT_CHANNELS

DEFAULT_CHAT_CHANNEL = "website"

# Approximate OpenAI pricing in USD per 1,000,000 tokens (input, output).
# Used for dashboard cost estimates; update when pricing changes.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
}
# Fallback rate when a logged model isn't in the table above.
DEFAULT_MODEL_PRICING: tuple[float, float] = (0.25, 2.00)


def estimate_cost_usd(model: str | None, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for a model's input/output token counts."""
    in_rate, out_rate = MODEL_PRICING.get(model or "", DEFAULT_MODEL_PRICING)
    return (prompt_tokens / 1_000_000) * in_rate + (completion_tokens / 1_000_000) * out_rate
