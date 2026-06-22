"""Shared AsyncOpenAI client.

A single client (and its underlying httpx connection pool) is reused across all
requests instead of constructing a new client per call, which avoids TLS/connection
churn under load. AsyncOpenAI is safe for concurrent use.
"""

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()
_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=30.0,
            max_retries=2,
        )
    return _client
