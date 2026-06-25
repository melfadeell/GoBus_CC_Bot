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
    # LLM routing: decides content/ticket intents from message + conversation context.
    chat_understanding_enabled: bool = True
    chat_understanding_model: str = "gpt-4o-mini"
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

    # --- CRM / ticketing (email + OTP) ---
    # When false, emails are NOT sent — they're logged (mock mode) so the feature
    # works end-to-end before real SMTP creds are supplied.
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "GoBus Support <no-reply@gobus.local>"
    smtp_use_tls: bool = True
    # Email-OTP for guest ticket creation/lookup.
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    # Model used by the in-app ticketing agent to classify + draft tickets.
    ticketing_model: str = "gpt-4o-mini"

    # --- Rate limits (slowapi strings; override via .env, e.g. RATE_LIMIT_CHAT="30/minute") ---
    rate_limit_chat: str = "15/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_customer_auth: str = "10/minute"
    rate_limit_ticket: str = "10/minute"
    rate_limit_otp_request: str = "5/minute"

    # --- Login lockout (shared by admin + customer auth) ---
    login_lockout_threshold: int = 5
    login_lockout_window_minutes: int = 15

    # --- Cost estimation: USD per 1M tokens (input, output) per model. Override the
    # whole map via the MODEL_PRICING env var as JSON, e.g.
    # MODEL_PRICING='{"gpt-4o-mini":[0.15,0.6]}'. default_model_pricing is the fallback. ---
    model_pricing: dict[str, tuple[float, float]] = {
        "gpt-5-mini": (0.25, 2.00),
        "gpt-5": (1.25, 10.00),
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1-mini": (0.40, 1.60),
    }
    default_model_pricing: tuple[float, float] = (0.25, 2.00)

    # --- Representative station per route city (trip departure/arrival defaults).
    # Override via the CITY_STATION_NAMES env var as JSON. ---
    city_station_names: dict[str, str] = {
        "القاهرة": "عبد المنعم رياض",
        "الإسكندرية": "سيدي جابر _ سموحة",
        "الأقصر": "الأقصر",
        "الساحل الشمالى": "مراسى (الساحل الشمالى)",
        "العين السخنة": "بورتو السخنة",
        "الغردقة": "الغردقة",
        "بورسعيد": "بورسعيد وسط البلد",
        "دهب": "دهب",
        "شرم الشيخ": "جوباص شرم",
        "مرسى علم": "مرسى علم",
        "مكادى": "مكادى",
        "نويبع": "نويبع",
    }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
