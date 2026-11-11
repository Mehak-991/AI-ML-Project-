"""Operator password reset (recovery when a superadmin password is lost). Server access only.

Usage:
    docker compose run --rm --no-deps -it app python scripts/reset_password.py --email you@example.com

The new password comes from RESET_PASSWORD or a hidden prompt (asked twice), never from argv, and
is never printed. All of the account's refresh tokens are revoked, and an audit entry is written
(actor "cli"). It changes nothing else about the account (role and status are untouched).

Exit codes: 0 done, 1 refused or invalid input, 2 configuration or database error.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASSWORD_ENV = "RESET_PASSWORD"  # noqa: S105 - the NAME of an environment variable, not a password


def _read_password() -> str | None:
    value = os.environ.get(PASSWORD_ENV)
    if value:
        return value
    if not sys.stdin.isatty():
        return None
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return None
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset one account's password (server-side only).")
    parser.add_argument("--email", required=True, help="Email of the account")
    args = parser.parse_args(argv)

    from app.core.config import load_settings
    from app.core.exceptions import AppError
    from app.database.session import get_session_factory
    from app.services import audit_service, auth_service

    try:
        settings = load_settings()
        if settings.DATABASE_URL is None:
            print("DATABASE_URL is not configured.", file=sys.stderr)
            return 2
    except Exception as exc:
        print(f"Configuration error: {type(exc).__name__}", file=sys.stderr)
        return 2

    password = _read_password()
    if not password:
        print(f"No password supplied. Set {PASSWORD_ENV} or run with an interactive terminal (-it).", file=sys.stderr)
        return 1

    try:
        with get_session_factory()() as session:
            if not audit_service.audit_table_exists(session):
                print("Refused: migration 0014 has not been applied (no audit_logs table).", file=sys.stderr)
                return 1
            user = auth_service.reset_password_by_operator(session, email=args.email, new_password=password)
            print(f"Password reset for {user.email}; its sessions were revoked.")
    except AppError as exc:
        print(f"Refused: {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Database error: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
