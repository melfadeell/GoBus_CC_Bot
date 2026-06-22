"""Application logging setup (text or JSON) configured from settings."""

import logging
import sys

from app.config import get_settings

settings = get_settings()


def _json_formatter() -> logging.Formatter:
    # python-json-logger moved the class between versions; support both.
    try:
        from pythonjsonlogger.json import JsonFormatter  # v3.1+/v4
    except Exception:  # pragma: no cover
        from pythonjsonlogger.jsonlogger import JsonFormatter  # older
    return JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format.lower() == "json":
        handler.setFormatter(_json_formatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Quiet noisy libraries a touch.
    logging.getLogger("httpx").setLevel(logging.WARNING)


# A dedicated logger for one-line metric events (structured-logs-only metrics).
metrics_logger = logging.getLogger("gobus.metrics")
