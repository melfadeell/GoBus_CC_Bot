from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://root:@localhost:3306/gobus_chatbot"
    logs_database_url: str = "mysql+pymysql://root:@localhost:3306/gobus_chatbot_logs"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    admin_email: str = "admin@gobus.local"
    admin_password: str = "admin123"
    website_data_path: str = "../Website data"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    tesseract_cmd: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
