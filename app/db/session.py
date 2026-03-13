from functools import lru_cache
from typing import Any, Dict

from sqlalchemy import create_engine, text

from app.core.config import get_settings


@lru_cache(maxsize=4)
def build_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def get_engine():
    return build_engine(get_settings().database_url)


def reset_engine_cache() -> None:
    build_engine.cache_clear()


def database_healthcheck() -> Dict[str, Any]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "detail": "database connection succeeded"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
