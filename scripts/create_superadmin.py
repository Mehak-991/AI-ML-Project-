"""One-time superadmin bootstrap and recovery. Run by an operator with server access ONLY.

There is deliberately no API for this: a superadmin can be created only here, or granted by an
existing superadmin through the authenticated API.

Usage (Docker; inside the stack's network so DATABASE_URL reaches the right database):
    # create a NEW superadmin account (password asked twice, hidden)
    docker compose run --rm --no-deps -it app python scripts/create_superadmin.py --email you@example.com

    # promote ONE explicitly named EXISTING account (you must confirm by typing its email, or pass --yes)
    docker compose run --rm --no-deps -it app python scripts/create_superadmin.py --email you@example.com --promote

Rules:
  * Refuses if an active superadmin already exists, so it is one-time. It is also the recovery path
    when every superadmin has been lost.
  * Refuses until migration 0014 has been applied (the audit table must exist).
  * Never selects an account for you. --promote needs the exact email and a confirmation.
  * Never changes an existing password. The password for a new account comes from
    BOOTSTRAP_SUPERADMIN_PASSWORD or a hidden prompt, never from argv, and is never printed.
  * Writes an audit entry (actor "cli").

Exit codes: 0 done, 1 refused or invalid input, 2 configuration or database error.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASSWORD_ENV = "BOOTSTRAP_SUPERADMIN_PASSWORD"


def _read_password() -> str | None:
    value = os.environ.get(PASSWORD_ENV)
    if value:
        return value
    if not sys.stdin.isatty():
        return None
    first = getpass.getpass("Superadmin password: ")
    if first != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return None
    return first


def _confirm_promotion(email: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("Promoting an existing account needs confirmation: use an interactive terminal (-it) or --yes.", file=sys.stderr)
        return False
    typed = input(f"Type the email of the account to promote to SUPERADMIN ({email}) to confirm: ")
    return typed.strip().lower() == email.strip().lower()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or promote the first superadmin (server-side only).")
    parser.add_argument("--email", required=True, help="Email of the new account, or of the existing account with --promote")
    parser.add_argument("--promote", action="store_true", help="Promote this EXISTING account instead of creating one")
    parser.add_argument("--yes", action="store_true", help="Confirm a promotion without the interactive prompt")
    parser.add_argument("--full-name", default="Superadmin", help="Display name for a new account")
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
    except Exception as exc:  # configuration errors never include secret values
        print(f"Configuration error: {type(exc).__name__}", file=sys.stderr)
        return 2

    password = None
    if args.promote:
        if not _confirm_promotion(args.email, args.yes):
            print("Not confirmed; nothing was changed.", file=sys.stderr)
            return 1
    else:
        password = _read_password()
        if not password:
            print(
                f"No password supplied. Set {PASSWORD_ENV} or run with an interactive terminal (-it).",
                file=sys.stderr,
            )
            return 1

    try:
        with get_session_factory()() as session:
            if not audit_service.audit_table_exists(session):
                print("Refused: migration 0014 has not been applied (no audit_logs table).", file=sys.stderr)
                return 1
            user = auth_service.bootstrap_superadmin(
                session,
                email=args.email,
                password=password,
                promote_existing=args.promote,
                full_name=args.full_name,
            )
            verb = "Promoted" if args.promote else "Created"
            print(f"{verb} superadmin {user.email} (id {user.id}).")
    except AppError as exc:
        print(f"Refused: {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Database error: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
