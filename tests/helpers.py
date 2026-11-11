"""Small helpers shared by tests."""

import io

import pandas as pd


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def write_bytes(path, data: bytes):
    path.write_bytes(data)
    return path


DEFAULT_TEST_PASSWORD = "Str0ngPassw0rd"


def insert_account(
    session_factory,
    email: str,
    role: str = "user",
    password: str = DEFAULT_TEST_PASSWORD,
    *,
    full_name: str = "",
    is_active: bool = True,
):
    """Create an account with an exact role directly in the database.

    Tests use this where production uses the server-side bootstrap: public registration can only
    ever create a ``user``, so an admin or superadmin has to be created out of band.
    """
    from app.core import security
    from app.database.models.user import User

    with session_factory() as session:
        user = User(
            email=email.lower(),
            hashed_password=security.hash_password(password),
            full_name=full_name,
            role=role,
            is_active=is_active,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
