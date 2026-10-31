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

from app.core import security
from app.database.models.user import User
from app.repositories.users import UserRepository

security_bearer = HTTPBearer(auto_error=False)
auth_logger = logging.getLogger("app.auth")


def get_current_user_optional(
    auth: Annotated[HTTPAuthorizationCredentials | None, Security(security_bearer)],
    db: DbSession,
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
        user = UserRepository(db).get(user_id)
        if not user or not user.is_active:
            return None
        return user
    except Exception:
        return None


def get_current_user(
    auth: Annotated[HTTPAuthorizationCredentials | None, Security(security_bearer)],
    db: DbSession,
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
        return user
    except HTTPException:
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


def require_role(*allowed_roles: str):
    """Factory dependency enforcing RBAC roles: 'admin', 'ml_engineer', 'viewer'."""

    def _role_checker(current_user: CurrentUserDep) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: role '{current_user.role}' lacks permission for this action. Required: {', '.join(allowed_roles)}.",
            )
        return current_user

    return _role_checker
