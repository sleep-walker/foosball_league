from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str
    ASYNC_DATABASE_URL: str
    TOKEN_LIFETIME: int = 10800
    DEBUG: bool = False

    # CORS — comma-separated origins, e.g. "http://localhost:3000,https://app.example.com"
    CORS_ORIGINS: str = ""

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
