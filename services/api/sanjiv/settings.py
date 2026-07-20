from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sanjiv_env: str = "development"
    sanjiv_log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://sanjiv:change-me-local-only@localhost:5432/sanjiv"
    )
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
