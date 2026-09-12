"""Container start-up: wait for the database, apply migrations, create the first admin.

Runs before the web server on every start, so pulling an update and restarting the
stack is enough to bring the schema up to date.
"""

from __future__ import annotations

import logging
import secrets
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .db import SessionLocal, engine
from .models import AppSetting, User
from .schemas import USERNAME
from .security import hash_password

SECRET_KEY_SETTING = "session_secret_key"

log = logging.getLogger("registry.bootstrap")
APP_ROOT = Path(__file__).resolve().parent.parent


def wait_for_database(timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    delay = 1.0
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            log.info("Connected to %s.", engine.dialect.name)
            return
        except SQLAlchemyError as exc:
            reason = str(getattr(exc, "orig", exc)).strip().splitlines()[0][:200]
            if time.monotonic() >= deadline:
                log.error("Gave up waiting for the database: %s", reason)
                raise
            log.info("Waiting for the database: %s", reason)
            time.sleep(delay)
            delay = min(delay * 1.5, 5.0)


def run_migrations() -> None:
    cfg = Config(str(APP_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(APP_ROOT / "migrations"))
    cfg.attributes["skip_logging_config"] = True
    command.upgrade(cfg, "head")
    log.info("Database schema is up to date.")


def read_secret_key() -> str | None:
    """The stored session key, or None if the app hasn't generated one yet."""
    with SessionLocal() as db:
        row = db.get(AppSetting, SECRET_KEY_SETTING)
        return row.value if row else None


def ensure_secret_key() -> None:
    """Generate and store a session key unless one was supplied in the environment.

    Keeping it in the database means sessions survive a redeploy, which matters
    when the stack is managed from Portainer and there is no .env file to hold it.
    """
    if get_settings().secret_key:
        return
    with SessionLocal() as db:
        if db.get(AppSetting, SECRET_KEY_SETTING) is None:
            db.add(AppSetting(key=SECRET_KEY_SETTING, value=secrets.token_urlsafe(48)))
            db.commit()
            log.info("Generated a session key and stored it in the database.")


def ensure_admin() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))):
            return
        username = settings.admin_username
        if not USERNAME.match(username):
            raise SystemExit("ADMIN_USERNAME must be 3-64 lowercase letters, numbers, dots, dashes or underscores.")
        password = settings.admin_password
        generated = False
        if len(password) < 10 or password.startswith("change-me"):
            if password:
                raise SystemExit("ADMIN_PASSWORD must be at least 10 characters.")
            password = secrets.token_urlsafe(9)
            generated = True
        db.add(User(username=username, password_hash=hash_password(password)))
        db.commit()
        if generated:
            # Printed once, for Portainer users who have no shell and no .env file.
            log.warning(
                "\n%s\n  First account created.\n    Username: %s\n    Password: %s\n"
                "  Sign in and change it. This is the only time it is shown.\n%s",
                "=" * 64, username, password, "=" * 64,
            )
        else:
            log.info("Created the first account: %s", username)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    wait_for_database()
    run_migrations()
    ensure_secret_key()
    ensure_admin()


if __name__ == "__main__":
    main()
