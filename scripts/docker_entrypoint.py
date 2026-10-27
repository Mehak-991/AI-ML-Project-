"""Container entrypoint: validate config, apply migrations (with retries), exec the server.

Environment:
  RUN_MIGRATIONS=true|false        apply `alembic upgrade head` before starting (default true)
  MIGRATION_MAX_ATTEMPTS=20        connection attempts while the database starts up
  MIGRATION_RETRY_SECONDS=3

Transient failures (connection refused, timeout, DNS) are retried; configuration
errors (bad password, missing database) fail fast so the container exits visibly.
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import load_settings  # noqa: E402
from app.core.exceptions import ConfigurationError  # noqa: E402

TRANSIENT = {"connection_refused", "timeout", "host_not_found", "unknown_error"}
DEFAULT_COMMAND = [
    "uvicorn",
    "app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--proxy-headers",
    "--no-access-log",  # the app writes its own structured access log
]


def log(message: str) -> None:
    print(f"[entrypoint] {message}", flush=True)


def run_migrations() -> None:
    from alembic.config import Config

    from alembic import command
    from app.database.session import diagnose_database, dispose_engine

    attempts = int(os.getenv("MIGRATION_MAX_ATTEMPTS", "20"))
    delay = float(os.getenv("MIGRATION_RETRY_SECONDS", "3"))
    for attempt in range(1, attempts + 1):
        result = diagnose_database()
        if result.ok:
            break
        if result.category not in TRANSIENT or attempt == attempts:
            log(f"database check failed ({result.category}): {result.hint}")
            sys.exit(3)
        log(f"database not ready ({result.category}); retry {attempt}/{attempts} in {delay:g}s")
        time.sleep(delay)
    dispose_engine()

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, "head")
    log("migrations applied")


def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        log(str(exc))
        sys.exit(2)
    log(f"environment={settings.APP_ENV}")
    if os.getenv("RUN_MIGRATIONS", "true").lower() == "true":
        if settings.DATABASE_URL is None:
            log("RUN_MIGRATIONS=true but DATABASE_URL is not set; skipping migrations")
        else:
            run_migrations()
    command = sys.argv[1:] or DEFAULT_COMMAND
    log(f"starting: {' '.join(command)}")
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
