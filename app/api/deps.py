"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.ai.classification import TextClassificationService
from app.ai.container import AIServices
from app.ai.embeddings import EmbeddingService
from app.ai.llm import ChatService
from app.ai.tokens import TokenCounter
from app.core.config import Settings, get_settings
from app.database.session import get_db

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]


def get_ai_services(request: Request) -> AIServices:
    return request.app.state.ai


AIServicesDep = Annotated[AIServices, Depends(get_ai_services)]


def get_embedding_service(ai: AIServicesDep) -> EmbeddingService:
    return ai.embedding_service


def get_text_classifier(ai: AIServicesDep) -> TextClassificationService:
    return ai.text_classification


def get_chat_service(ai: AIServicesDep) -> ChatService:
    return ai.chat_service()


def get_token_counter(ai: AIServicesDep) -> TokenCounter:
    return ai.token_counter


import logging
import uuid

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import security
from app.core.permissions import Permission, effective_role, has_permission
from collections.abc import Generator
from app.core.exceptions import DatabaseNotConfiguredError
from app.database.models.user import User
from app.repositories.users import UserRepository

security_bearer = HTTPBearer(auto_error=False)
auth_logger = logging.getLogger("app.auth")


def get_db_optional(request: Request) -> Generator[Session | None, None, None]:
    override = request.app.dependency_overrides.get(get_db)
    if override:
        res = override()
        if hasattr(res, "__next__"):
            session = next(res)
            try:
                yield session
            finally:
                try:
                    next(res)
                except StopIteration:
                    pass
        else:
            yield res
        return
    settings = get_settings()
    if settings.DATABASE_URL is None:
        yield None
        return
    yield from get_db()


DbOptionalSession = Annotated[Session | None, Depends(get_db_optional)]


def _load_user(db: Session, user_id: uuid.UUID) -> User | None:
    """Look the user up on the auth session, then give its connection back to the pool.

    This session is separate from the route's. Holding it for the whole request would make
    every authenticated request occupy two pooled connections. Sessions use
    expire_on_commit=False, so the returned user stays readable.
    """
    user = UserRepository(db).get(user_id)
    db.commit()
    return user


def get_current_user_optional(
    auth: Annotated[HTTPAuthorizationCredentials | None, Security(security_bearer)],
    db: DbOptionalSession,
    settings: SettingsDep,
) -> User | None:
    if not auth or not auth.credentials:
        return None
    try:
        payload = security.decode_access_token(auth.credentials, settings)
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
        if db is None:
            return None
        user = _load_user(db, user_id)
        if not user or not user.is_active:
            return None
        return user
    except (jwt.PyJWTError, ValueError):
        return None


def get_current_user(
    auth: Annotated[HTTPAuthorizationCredentials | None, Security(security_bearer)],
    db: DbOptionalSession,
    settings: SettingsDep,
) -> User:
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = security.decode_access_token(auth.credentials, settings)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        # Parser details stay server-side; never log the token itself.
        auth_logger.warning(
            "Access token rejected: %s", type(exc).__name__, extra={"error_type": type(exc).__name__}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    # Outside the try: a database outage must surface as 503, not as a rejected token
    # (a 401 makes clients throw away a perfectly valid session).
    if db is None:
        raise DatabaseNotConfiguredError()
    user = _load_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentUserOptionalDep = Annotated[User | None, Depends(get_current_user_optional)]


POLICY_ATTR = "__rbac_policy__"


def _declare_policy(func, policy: tuple[str, Permission | None]):
    setattr(func, POLICY_ATTR, policy)
    return func


def require_permission(permission: Permission):
    """Dependency factory: the caller must hold ``permission``. Returns the authenticated user.

    Unauthenticated callers get 401 from ``get_current_user`` before this runs; authenticated
    callers without the permission get 403. Routes never compare role names.
    """

    def _permission_checker(current_user: CurrentUserDep) -> User:
        if not has_permission(current_user.role, permission):
            role = effective_role(current_user.role)
            auth_logger.info(
                "denied: role=%s lacks %s", role.value if role else "unknown", permission.value
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access forbidden: your role ({role.value if role else 'unknown'}) lacks the "
                    f"'{permission.value}' permission."
                ),
            )
        return current_user

    return _declare_policy(_permission_checker, ("permission", permission))


def public_route() -> None:
    """Marks a route as intentionally reachable without authentication."""


_declare_policy(public_route, ("public", None))

# Usable as a parameter dependency or in ``dependencies=[...]``.
PublicRoute = Depends(public_route)

# Common permission dependencies; the value is the authenticated User.
ReadAccessDep = Annotated[User, Depends(require_permission(Permission.RESOURCES_READ))]
PredictAccessDep = Annotated[User, Depends(require_permission(Permission.PREDICT))]
MlOperatorDep = Annotated[User, Depends(require_permission(Permission.ML_OPERATE))]
DeploymentManagerDep = Annotated[User, Depends(require_permission(Permission.DEPLOYMENTS_MANAGE))]
ProfileDep = Annotated[User, Depends(require_permission(Permission.PROFILE_MANAGE))]


def _declared_policies(dependant) -> list[tuple[str, Permission | None]]:
    found: list[tuple[str, Permission | None]] = []
    for sub in dependant.dependencies:
        policy = getattr(sub.call, POLICY_ATTR, None)
        if policy is not None:
            found.append(policy)
        found.extend(_declared_policies(sub))
    return found


_policy_cache: dict[int, bool] = {}


def route_has_policy(route) -> bool:
    """True if the route declares a permission or is explicitly public."""
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return False
    return bool(_declared_policies(dependant))


def enforce_route_policy(request: Request) -> None:
    """Deny-by-default: an API route that declares neither a permission nor ``public_route`` is
    refused (403) instead of being served. Applied to the whole application.

    Fails closed: if the matched route cannot be inspected, the request is denied too.
    """
    route = request.scope.get("route")
    if route is None:
        # Not matched to an API route (for example the documentation pages), nothing to enforce.
        return
    key = id(route)
    declared = _policy_cache.get(key)
    if declared is None:
        declared = _policy_cache[key] = route_has_policy(route)
    if not declared:
        auth_logger.error(
            "route %s %s declares no access policy; denied",
            request.method,
            getattr(route, "path", "?"),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: this route has no declared access policy.",
        )
