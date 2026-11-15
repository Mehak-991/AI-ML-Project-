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

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from collections.abc import Generator

from app.core import security
from app.core.exceptions import (
    DatabaseNotConfiguredError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from app.core.permissions import (
    ROLE_VALUES,
    WRITE_PERMISSIONS,
    Permission,
    has_permission,
    is_super_admin,
)
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


def _token_version_matches(payload: dict, user: User) -> bool:
    # Tokens issued before token versioning carry no "ver"; they match version 0 only.
    return payload.get("ver", 0) == user.token_version


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
        user = UserRepository(db).get(user_id)
        if not user or not user.is_active or not _token_version_matches(payload, user):
            return None
        return user
    except Exception:
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
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = uuid.UUID(user_id_str)
        if db is None:
            raise DatabaseNotConfiguredError()
        user = UserRepository(db).get(user_id)
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
        if not _token_version_matches(payload, user):
            # Password/role changed or account deactivated since this token was issued.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is no longer valid. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except HTTPException:
        raise
    except DatabaseNotConfiguredError:
        raise
    except Exception as exc:
        # Parser details stay server-side; never log the token itself.
        auth_logger.warning(
            "Access token rejected: %s", type(exc).__name__, extra={"error_type": type(exc).__name__}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentUserOptionalDep = Annotated[User | None, Depends(get_current_user_optional)]


class MaintenanceModeError(ServiceUnavailableError):
    code = "maintenance_mode"
    message = "The application is in maintenance mode; changes are temporarily disabled."


def _ensure_not_in_maintenance(db: Session | None, user: User) -> None:
    from app.services import settings_service

    if is_super_admin(user.role) or db is None:
        return
    if settings_service.get_value(db, "maintenance_mode"):
        raise MaintenanceModeError()


def require_permission(permission: Permission):
    """Dependency factory: the authenticated user's *stored* role must grant `permission`.

    The role comes from the database row loaded in get_current_user, never from the token
    or the request. Write permissions are additionally blocked in maintenance mode for
    everyone except super admins.
    """

    def _permission_checker(current_user: CurrentUserDep, db: DbOptionalSession) -> User:
        if not has_permission(current_user.role, permission):
            auth_logger.info(
                "Permission denied",
                extra={"permission": permission.value, "role": current_user.role},
            )
            raise PermissionDeniedError(
                "Access forbidden: your role does not permit this action.",
                details={"required_permission": permission.value},
            )
        if permission in WRITE_PERMISSIONS:
            _ensure_not_in_maintenance(db, current_user)
        return current_user

    _permission_checker.__name__ = f"require_{permission.name.lower()}"
    return _permission_checker


def require_role(*allowed_roles: str):
    """Dependency factory restricting an endpoint to explicit roles.

    Prefer require_permission; this exists for the rare endpoint tied to a role itself.
    """
    unknown = set(allowed_roles) - set(ROLE_VALUES)
    if unknown:
        raise ValueError(f"Unknown roles: {sorted(unknown)}")

    def _role_checker(current_user: CurrentUserDep) -> User:
        if current_user.role not in allowed_roles:
            raise PermissionDeniedError(
                "Access forbidden: your role does not permit this action.",
            )
        return current_user

    return _role_checker


# Ready-made annotated dependencies for route signatures.
MLReader = Annotated[User, Depends(require_permission(Permission.ML_READ))]
MLWriter = Annotated[User, Depends(require_permission(Permission.ML_WRITE))]
MLDeployer = Annotated[User, Depends(require_permission(Permission.ML_DEPLOY))]
