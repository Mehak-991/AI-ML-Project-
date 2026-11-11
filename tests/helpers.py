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


def iter_api_routes(app):
    """Yield (method, path, route_like) for every API route of a FastAPI app.

    Works with older FastAPI (a flat list of APIRoute) and with releases that wrap included
    routers in lazy objects exposing ``effective_route_contexts()``. ``route_like`` always has
    ``.dependant`` and ``.endpoint``. HEAD and OPTIONS are skipped.
    """

    def visit(obj):
        if hasattr(obj, "effective_route_contexts"):
            for ctx in obj.effective_route_contexts():
                yield from visit(ctx)
            return
        dependant = getattr(obj, "dependant", None)
        methods = getattr(obj, "methods", None)
        path = getattr(obj, "path", None) or getattr(obj, "path_format", None)
        if dependant is None or not methods or path is None:
            return
        for method in sorted(set(methods) - {"HEAD", "OPTIONS"}):
            yield method, path, obj

    for route in app.routes:
        yield from visit(route)
