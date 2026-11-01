"""Authentication routes for registration, login, token refresh, and user profile."""

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUserDep, CurrentUserOptionalDep, DbSession, SettingsDep, require_role
from app.repositories.users import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserList,
    UserLoginRequest,
    UserRead,
    UserRegisterRequest,
    UserUpdateRequest,
)
from app.schemas.common import ErrorResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Authentication failed or token invalid"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Insufficient permissions"}}
CONFLICT = {409: {"model": ErrorResponse, "description": "User already exists"}}


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    responses=CONFLICT | FORBIDDEN,
)
def register(
    request: UserRegisterRequest, db: DbSession, current_user: CurrentUserOptionalDep
) -> UserRead:
    user = auth_service.register_user(db, request, requested_by=current_user)
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
    responses=UNAUTHORIZED,
)
def login(request: UserLoginRequest, db: DbSession, settings: SettingsDep) -> TokenResponse:
    _, token_resp = auth_service.authenticate_user(db, settings, request)
    return token_resp


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using a valid refresh token",
    responses=UNAUTHORIZED,
)
def refresh(request: RefreshTokenRequest, db: DbSession, settings: SettingsDep) -> TokenResponse:
    return auth_service.refresh_access_token(db, settings, request)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out and revoke refresh token",
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
    request: ChangePasswordRequest, db: DbSession, current_user: CurrentUserDep
) -> dict[str, str]:
    auth_service.change_password(
        db, current_user, request.current_password, request.new_password
    )
    return {"message": "Password changed. All sessions must log in again."}


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get current authenticated user profile",
    responses=UNAUTHORIZED,
)
def get_me(current_user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(current_user)


# --- User Administration Endpoints (Admin role only) ---


@router.get(
    "/users",
    response_model=UserList,
    summary="List and filter users (Admin only)",
    responses=UNAUTHORIZED | FORBIDDEN,
    dependencies=[Depends(require_role("admin"))],
)
def list_users(
    db: DbSession,
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> UserList:
    repo = UserRepository(db)
    items = repo.list_filtered(
        role=role, is_active=is_active, query=search, offset=offset, limit=limit
    )
    total = repo.count_filtered(role=role, is_active=is_active, query=search)
    return UserList(
        items=[UserRead.model_validate(u) for u in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Update user role or status (Admin only)",
    responses=UNAUTHORIZED | FORBIDDEN,
    dependencies=[Depends(require_role("admin"))],
)
def update_user(
    user_id: uuid.UUID,
    request: UserUpdateRequest,
    current_user: CurrentUserDep,
    db: DbSession,
) -> UserRead:
    updated = auth_service.update_user_by_admin(db, current_user.id, user_id, request)
    return UserRead.model_validate(updated)
