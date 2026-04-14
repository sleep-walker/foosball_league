from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str
    ASYNC_DATABASE_URL: str
    TOKEN_LIFETIME: int = 10800
    DEBUG: bool = False

    # Public URL — used for QR codes, email links, etc.
    BASE_URL: str = "http://localhost:8000"

    # CORS — comma-separated origins, e.g. "http://localhost:3000,https://app.example.com"
    CORS_ORIGINS: str = ""

    # Logging — DEBUG, INFO, WARNING, ERROR
    LOG_LEVEL: str = "INFO"
    # Log file — if set, logs are written to this file (in addition to stderr)
    LOG_FILE: str = ""

    # Admin bootstrap — the first user with this email gets superuser + auto-verified.
    # Set in .env: ADMIN_EMAIL=admin@example.com
    ADMIN_EMAIL: str = ""

    # Auto-verify all users (useful for development, disable in production)
    AUTO_VERIFY_USERS: bool = False

    # SMTP / e-mail
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_STARTTLS: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
