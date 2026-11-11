"""Authentication routes for registration, login, token refresh, profile and user administration.

Every route declares its access policy: ``public_route`` for the few unauthenticated ones, or a
permission from ``app.core.permissions``. User administration is superadmin-only; public
registration can only ever create a read-only ``user``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import (
    DbSession,
    ProfileDep,
    PublicRoute,
    SettingsDep,
    require_permission,
)
from app.core.permissions import Permission
from app.database.models.user import User
from app.repositories.users import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    RefreshTokenRequest,
    SelfUpdateRequest,
    TokenResponse,
    UserCreateRequest,
    UserList,
    UserLoginRequest,
    UserRead,
    UserRegisterRequest,
    UserUpdateRequest,
)
from app.schemas.common import ErrorResponse
from app.services import audit_service, auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Authentication failed or token invalid"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Insufficient permissions"}}
CONFLICT = {409: {"model": ErrorResponse, "description": "Conflict with the current state"}}

UserReaderDep = Annotated[User, Depends(require_permission(Permission.USERS_READ))]
UserManagerDep = Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))]
SuperadminGrantorDep = Annotated[User, Depends(require_permission(Permission.SUPERADMIN_GRANT))]


def _audit_context(request: Request) -> audit_service.AuditContext:
    return audit_service.AuditContext.for_request(request.client.host if request.client else None)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account (always a read-only user)",
    responses=CONFLICT,
    dependencies=[PublicRoute],
)
def register(request: UserRegisterRequest, db: DbSession, settings: SettingsDep) -> UserRead:
    user = auth_service.register_user(db, request, settings)
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
    responses=UNAUTHORIZED,
    dependencies=[PublicRoute],
)
def login(request: UserLoginRequest, db: DbSession, settings: SettingsDep) -> TokenResponse:
    _, token_resp = auth_service.authenticate_user(db, settings, request)
    return token_resp


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using a valid refresh token",
    responses=UNAUTHORIZED,
    dependencies=[PublicRoute],
)
def refresh(request: RefreshTokenRequest, db: DbSession, settings: SettingsDep) -> TokenResponse:
    return auth_service.refresh_access_token(db, settings, request)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out and revoke refresh token",
    dependencies=[PublicRoute],
)
def logout(request: RefreshTokenRequest, db: DbSession) -> dict[str, str]:
    auth_service.revoke_refresh_token(db, request.refresh_token)
    return {"message": "Successfully logged out."}


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
    summary="Change own password and revoke all of own refresh tokens",
    responses=UNAUTHORIZED,
)
def change_password(
    request: ChangePasswordRequest, db: DbSession, current_user: ProfileDep
) -> dict[str, str]:
    auth_service.change_password(db, current_user, request.current_password, request.new_password)
    return {"message": "Password changed. All sessions must log in again."}


@router.get(
    "/me",
    response_model=UserRead,
    summary="Current user, including the permissions computed for their role",
    responses=UNAUTHORIZED,
)
def get_me(current_user: ProfileDep) -> UserRead:
    return UserRead.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserRead,
    summary="Update own display name (never a role or status)",
    responses=UNAUTHORIZED,
)
def update_me(
    request: SelfUpdateRequest, http_request: Request, db: DbSession, current_user: ProfileDep
) -> UserRead:
    updated = auth_service.update_own_profile(db, current_user, request, _audit_context(http_request))
    return UserRead.model_validate(updated)


# --- User administration (superadmin only) ---


@router.get(
    "/users",
    response_model=UserList,
    summary="List and filter users (superadmin only)",
    responses=UNAUTHORIZED | FORBIDDEN,
)
def list_users(
    _actor: UserReaderDep,
    db: DbSession,
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> UserList:
    repo = UserRepository(db)
    items = repo.list_filtered(role=role, is_active=is_active, query=search, offset=offset, limit=limit)
    total = repo.count_filtered(role=role, is_active=is_active, query=search)
    return UserList(
        items=[UserRead.model_validate(u) for u in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account with role user or admin (superadmin only)",
    responses=UNAUTHORIZED | FORBIDDEN | CONFLICT,
)
def create_user(
    request: UserCreateRequest,
    http_request: Request,
    actor: UserManagerDep,
    db: DbSession,
    settings: SettingsDep,
) -> UserRead:
    created = auth_service.create_user(db, actor, request, settings, _audit_context(http_request))
    return UserRead.model_validate(created)


@router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Change a user's role (user/admin), active status or name (superadmin only)",
    responses=UNAUTHORIZED | FORBIDDEN | CONFLICT,
)
def update_user(
    user_id: uuid.UUID,
    request: UserUpdateRequest,
    http_request: Request,
    actor: UserManagerDep,
    db: DbSession,
    settings: SettingsDep,
) -> UserRead:
    updated = auth_service.update_user(
        db, actor, user_id, request, settings, _audit_context(http_request)
    )
    return UserRead.model_validate(updated)


@router.post(
    "/users/{user_id}/superadmin",
    response_model=UserRead,
    summary="Grant superadmin to an active account (existing superadmin only)",
    responses=UNAUTHORIZED | FORBIDDEN | CONFLICT,
)
def grant_superadmin(
    user_id: uuid.UUID, http_request: Request, actor: SuperadminGrantorDep, db: DbSession
) -> UserRead:
    updated = auth_service.grant_superadmin(db, actor, user_id, _audit_context(http_request))
    return UserRead.model_validate(updated)


@router.delete(
    "/users/{user_id}/superadmin",
    response_model=UserRead,
    summary="Revoke superadmin (becomes admin); the last superadmin is protected",
    responses=UNAUTHORIZED | FORBIDDEN | CONFLICT,
)
def revoke_superadmin(
    user_id: uuid.UUID, http_request: Request, actor: SuperadminGrantorDep, db: DbSession
) -> UserRead:
    updated = auth_service.revoke_superadmin(db, actor, user_id, _audit_context(http_request))
    return UserRead.model_validate(updated)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hard-delete a deactivated account that owns nothing (superadmin only; explicit confirmation)",
    responses=UNAUTHORIZED | FORBIDDEN | CONFLICT,
)
def delete_user(
    user_id: uuid.UUID,
    http_request: Request,
    actor: UserManagerDep,
    db: DbSession,
    confirm_email: Annotated[str, Query(min_length=3, max_length=255)],
) -> Response:
    auth_service.delete_user(db, actor, user_id, confirm_email, _audit_context(http_request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
