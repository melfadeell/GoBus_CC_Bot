from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://root:@localhost:3306/gobus_chatbot"
    logs_database_url: str = "mysql+pymysql://root:@localhost:3306/gobus_chatbot_logs"
    openai_api_key: str = ""
    # Custom OpenAI-compatible endpoint base URL (blank = OpenAI default).
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    # Fast, cheap model used only to clean/correct the user's query before retrieval.
    query_rewrite_model: str = "gpt-4o-mini"
    query_rewrite_enabled: bool = True
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    admin_email: str = "admin@gobus.local"
    admin_password: str = "admin123"
    website_data_path: str = "../Website data"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    tesseract_cmd: str = ""

    # --- Production hardening (Phase 1+) ---
    # Redis URL for cross-worker rate limiting; blank/unreachable → in-memory fallback.
    redis_url: str = "redis://localhost:6379"
    # SQLAlchemy connection pool sizing (per worker), for the two engines.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    # In-process TTL (seconds) for cached reference data (routes/stations/etc.).
    reference_cache_ttl: int = 60
    # Expose the compiled trips SQL to the chat UI (debug only; keep off in prod).
    expose_sql_debug: bool = False
    # Logging (Phase 4): level + json|text format.
    log_level: str = "INFO"
    log_format: str = "text"
    # Retention / refresh windows (Phase 4 scheduler).
    log_retention_days: int = 30
    upload_retention_days: int = 30
    trip_refresh_days: int = 14
    app_version: str = "1.0.0"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
