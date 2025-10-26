from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "supersecret"
    DATABASE_URL: str = "sqlite:///./sql_app.db"
    ASYNC_DATABASE_URL: str = "sqlite+aiosqlite:///./sql_app.db"
    TOKEN_LIFETIME: int = 10800
    DEBUG: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()


def get_settings() -> Settings:
    return settings
