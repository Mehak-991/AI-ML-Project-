"""LEGACY (pre-RBAC-v2): create the first `admin`. Use scripts/create_superadmin.py instead.

After RBAC v2 an `admin` cannot manage users, so a fresh deployment needs a superadmin.
This script is kept only for stacks that have not migrated yet. It is one-time, run by an
operator with shell access.

Usage (Docker, inside the stack's network so DATABASE_URL points at the right database):
    docker compose run --rm --no-deps -it app python scripts/create_admin.py --email admin@example.com
    # non-interactive: pass the password through the environment, not the command line
    docker compose run --rm --no-deps -e BOOTSTRAP_ADMIN_PASSWORD app python scripts/create_admin.py --email ...

Rules:
  * Refuses if an active administrator already exists (it is not a way to add more admins).
  * Refuses if the email is already registered. It never promotes or changes an existing account.
  * The password is read from BOOTSTRAP_ADMIN_PASSWORD or a hidden prompt, never from argv, and is
    never printed or logged.

Exit codes: 0 created, 1 refused or invalid input, 2 configuration or database error.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASSWORD_ENV = "BOOTSTRAP_ADMIN_PASSWORD"  # noqa: S105 - the NAME of an environment variable, not a password


def _read_password() -> str | None:
    value = os.environ.get(PASSWORD_ENV)
    if value:
        return value
    if not sys.stdin.isatty():
        return None
    first = getpass.getpass("Administrator password: ")
    if first != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return None
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the first administrator account.")
    parser.add_argument("--email", required=True, help="Administrator email address")
    parser.add_argument("--full-name", default="Administrator", help="Display name")
    args = parser.parse_args(argv)

    from app.core.config import load_settings
    from app.core.exceptions import AppError
    from app.database.session import get_session_factory
    from app.services import auth_service

    try:
        settings = load_settings()
        if settings.DATABASE_URL is None:
            print("DATABASE_URL is not configured.", file=sys.stderr)
            return 2
    except Exception as exc:  # configuration errors never include secret values
        print(f"Configuration error: {type(exc).__name__}", file=sys.stderr)
        return 2

    password = _read_password()
    if not password:
        print(
            f"No password supplied. Set {PASSWORD_ENV} or run with an interactive terminal (-it).",
            file=sys.stderr,
        )
        return 1

    try:
        with get_session_factory()() as session:
            user = auth_service.create_bootstrap_admin(
                session, email=args.email, password=password, full_name=args.full_name
            )
            print(f"Created administrator {user.email} (id {user.id}).")
    except AppError as exc:
        print(f"Refused: {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Database error: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
