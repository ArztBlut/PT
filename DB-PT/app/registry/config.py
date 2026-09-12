"""Runtime configuration, read from environment variables set in compose.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.engine import URL, make_url

ENGINE_ALIASES = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "pg": "postgres",
    "mariadb": "mariadb",
    "mysql": "mariadb",
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    try:
        return int(value) if value else default
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a whole number (got {value!r})") from exc


@dataclass(frozen=True)
class Settings:
    db_engine: str
    database_url: URL
    secret_key: str
    admin_username: str
    admin_password: str
    app_title: str
    session_https_only: bool
    session_max_age: int


@lru_cache
def get_settings() -> Settings:
    raw_engine = _env("DB_ENGINE", "postgres").lower()
    engine = ENGINE_ALIASES.get(raw_engine)
    if engine is None:
        raise RuntimeError(f"DB_ENGINE must be 'postgres' or 'mariadb' (got {raw_engine!r})")

    db_password = os.environ.get("DB_PASSWORD", "")
    override = _env("DATABASE_URL")
    if override:
        url = make_url(override)
    else:
        if not db_password or db_password.startswith("change-me"):
            raise RuntimeError("DB_PASSWORD is not set. Run ./install.sh or edit .env.")
        common = {
            "username": _env("DB_USER", "personnel"),
            "password": db_password,
            "host": _env("DB_HOST", "db"),
            "database": _env("DB_NAME", "personnel"),
        }
        if engine == "postgres":
            url = URL.create("postgresql+psycopg", port=_env_int("DB_INTERNAL_PORT", 5432), **common)
        else:
            url = URL.create(
                "mariadb+pymysql",
                port=_env_int("DB_INTERNAL_PORT", 3306),
                query={"charset": "utf8mb4"},
                **common,
            )

    # Optional. When it isn't supplied the app generates one on first start and
    # keeps it in the database, so Portainer users don't have to invent one.
    secret_key = os.environ.get("SECRET_KEY", "")
    if secret_key and (len(secret_key) < 32 or secret_key.startswith("change-me")):
        raise RuntimeError("SECRET_KEY, if set, must be a random value of at least 32 characters.")

    session_hours = max(1, _env_int("SESSION_HOURS", 12))

    return Settings(
        db_engine=engine,
        database_url=url,
        secret_key=secret_key,
        admin_username=_env("ADMIN_USERNAME", "admin").lower(),
        admin_password=os.environ.get("ADMIN_PASSWORD", ""),
        app_title=(_env("APP_TITLE", "Personnel Registry") or "Personnel Registry")[:60],
        session_https_only=_env_bool("SESSION_HTTPS_ONLY", False),
        session_max_age=session_hours * 3600,
    )
