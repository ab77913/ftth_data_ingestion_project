from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg2://ftth:ftth@localhost:5432/ftth",
        alias="DATABASE_URL",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    default_customer_id: str = Field(default="demo_customer", alias="DEFAULT_CUSTOMER_ID")
    dispatch_batch_size: int = Field(default=100, alias="DISPATCH_BATCH_SIZE")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
