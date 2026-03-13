from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "JBNU Scholarship Regulation Search & Eligibility Decision System"
    environment: str = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://jbnu:jbnu@localhost:54329/jbnu_scholarship"
    raw_storage_path: str = "./data/raw"

    model_config = SettingsConfigDict(
        env_prefix="JBNU_",
        case_sensitive=False,
        env_file=".env",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
