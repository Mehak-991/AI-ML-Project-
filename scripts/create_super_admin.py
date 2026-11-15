"""Create the first Super Admin, or promote an existing account (reads DATABASE_URL).

This is the supported way to bootstrap production, where public registration never
grants privileges (AUTH_BOOTSTRAP_VIA_REGISTRATION defaults to off in production).

Usage:
    python scripts/create_super_admin.py --email admin@example.com --full-name "Ops Admin"
        Prompts for the password (twice). For automation, set SUPER_ADMIN_PASSWORD instead.
    python scripts/create_super_admin.py --email existing@example.com --promote
        Promotes an existing account to super_admin and ends its sessions.

The password is never printed or logged. Exit code 0 on success, 1 on failure.
"""

import argparse
import getpass
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core import security
from app.core.exceptions import DataValidationError
from app.core.permissions import Role
from app.database.models.user import User
from app.database.session import get_session_factory
from app.repositories.users import RefreshTokenRepository, UserRepository
from app.services import audit_service


def _read_password() -> str:
    from_env = os.environ.get("SUPER_ADMIN_PASSWORD")
    if from_env:
        return from_env
    if not sys.stdin.isatty():
        raise SystemExit("No TTY: set SUPER_ADMIN_PASSWORD to provide the password.")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", default="")
    parser.add_argument(
        "--promote", action="store_true", help="Promote an existing account instead of creating one"
    )
    args = parser.parse_args(argv)

    try:
        email = str(TypeAdapter(EmailStr).validate_python(args.email)).lower().strip()
    except ValidationError:
        print("Invalid email address.", file=sys.stderr)
        return 1

    with get_session_factory()() as session:
        repo = UserRepository(session)
        existing = repo.get_by_email(email)

        if args.promote:
            if existing is None:
                print(f"No account with email {email}.", file=sys.stderr)
                return 1
            old_role = existing.role
            existing.role = Role.SUPER_ADMIN.value
            existing.is_active = True
            existing.token_version += 1
            RefreshTokenRepository(session).revoke_all_for_user(existing.id)
            audit_service.record(
                session,
                actor=None,
                actor_email="cli:create_super_admin",
                action="user.promote_cli",
                category="user_admin",
                target_type="user",
                target_id=existing.id,
                details={"email": email, "old_role": old_role, "new_role": existing.role},
            )
            session.commit()
            print(f"Promoted {email} to super_admin (was {old_role}).")
            return 0

        if existing is not None:
            print(f"{email} already exists; use --promote to elevate it.", file=sys.stderr)
            return 1

        password = _read_password()
        try:
            security.validate_password_strength(password)
        except DataValidationError as exc:
            print(exc.message, file=sys.stderr)
            return 1

        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=security.hash_password(password),
            full_name=args.full_name.strip(),
            role=Role.SUPER_ADMIN.value,
            is_active=True,
            token_version=0,
        )
        repo.add(user)
        audit_service.record(
            session,
            actor=None,
            actor_email="cli:create_super_admin",
            action="user.create_cli",
            category="user_admin",
            target_type="user",
            target_id=user.id,
            details={"email": email, "role": user.role},
        )
        session.commit()
        print(f"Created super_admin {email}.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
