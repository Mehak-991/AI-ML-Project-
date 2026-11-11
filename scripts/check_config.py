"""Check configuration and environment before running or deploying.

Usage: python scripts/check_config.py [--db]
  --db   also connect to the database and compare its migration revision with head

Exit code 1 if any ERROR is found. Secrets are never printed.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.optional import EXTRA_FOR_MODULE, is_available  # noqa: E402
from app.core.config import Settings, load_settings  # noqa: E402
from app.core.exceptions import ConfigurationError  # noqa: E402


class Report:
    def __init__(self) -> None:
        self.errors = 0

    def ok(self, message: str) -> None:
        print(f"  OK     {message}")

    def info(self, message: str) -> None:
        print(f"  INFO   {message}")

    def warn(self, message: str) -> None:
        print(f"  WARN   {message}")

    def error(self, message: str) -> None:
        self.errors += 1
        print(f"  ERROR  {message}")


def check_settings(s: Settings, r: Report) -> None:
    r.ok(f"settings loaded (APP_ENV={s.APP_ENV}, LOG_FORMAT={s.LOG_FORMAT})")
    prod = s.is_production
    if prod and s.DOCS_ENABLED:
        r.warn("DOCS_ENABLED=true in production exposes the API schema publicly")
    if prod and s.LOG_FORMAT != "json":
        r.warn("LOG_FORMAT=json is recommended in production")
    if prod and not s.RATE_LIMIT_ENABLED:
        r.warn("RATE_LIMIT_ENABLED=false in production (rely on a gateway limiter?)")
    if prod and s.MODEL_COMPATIBILITY_CHECK != "strict":
        r.warn("MODEL_COMPATIBILITY_CHECK=warn may serve models pickled by other sklearn versions")
    if s.LLM_LOG_CONTENT:
        r.warn("LLM_LOG_CONTENT=true writes prompts and completions to the logs")
    r.info(f"CORS origins: {s.cors_origins or 'none (browser cross-origin calls blocked)'}")
    if s.DATABASE_URL is None:
        r.warn("DATABASE_URL not set: dataset/model endpoints will return 503")
    if s.OPENAI_API_KEY is None:
        r.info("OPENAI_API_KEY not set: /llm/chat and /nlp/analyze will return 503")
    else:
        r.ok(f"OpenAI key configured; model={s.OPENAI_MODEL}; allowed={s.allowed_llm_models}")


def check_directories(s: Settings, r: Report) -> None:
    for label, directory in (("UPLOAD_DIR", s.UPLOAD_DIR), ("MODEL_DIR", s.MODEL_DIR)):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory):
                pass
            r.ok(f"{label} writable: {directory.resolve()}")
        except OSError as exc:
            r.error(f"{label} not writable ({directory}): {type(exc).__name__}")


def check_packages(r: Report) -> None:
    for module in sorted(EXTRA_FOR_MODULE):
        state = "installed" if is_available(module) else "not installed"
        r.info(f"optional {module:<26} {state}")


def check_database(r: Report) -> None:
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from app.database.session import diagnose_database, get_engine

    result = diagnose_database()
    if not result.ok:
        r.error(f"database: {result.category} - {result.hint}")
        return
    r.ok(f"database reachable ({result.server_version}, {result.latency_ms} ms)")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    with get_engine().connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current == head:
        r.ok(f"migrations up to date (revision {head})")
    else:
        r.error(f"database at revision {current}, code expects {head}: run `alembic upgrade head`")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", action="store_true")
    args = parser.parse_args()
    report = Report()

    print("Configuration")
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        report.error(str(exc))
        return 1
    check_settings(settings, report)
    if Path(".env").exists() and os.name != "nt" and Path(".env").stat().st_mode & 0o077:
        report.warn(".env is readable by other users (chmod 600 .env)")

    print("Storage")
    check_directories(settings, report)
    print("Optional AI packages")
    check_packages(report)
    if args.db:
        print("Database")
        check_database(report)

    print(f"\n{'FAILED' if report.errors else 'PASSED'} ({report.errors} error(s))")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
