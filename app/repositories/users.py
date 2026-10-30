import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.user import RefreshToken, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.lower().strip())
        return self.session.scalars(stmt).first()

    def count_active_admins(self) -> int:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.is_active == True)
        )
        return self.session.scalar(stmt) or 0

    def list_filtered(
        self,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[User]:
        stmt = select(User)
        if role is not None:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        if query:
            q = f"%{query.lower().strip()}%"
            stmt = stmt.where(func.lower(User.email).like(q) | func.lower(User.full_name).like(q))

        stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
        return self.session.scalars(stmt).all()

    def count_filtered(
        self,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        query: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(User)
        if role is not None:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        if query:
            q = f"%{query.lower().strip()}%"
            stmt = stmt.where(func.lower(User.email).like(q) | func.lower(User.full_name).like(q))

        return self.session.scalar(stmt) or 0


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self.session.scalars(stmt).first()

    def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        stmt = select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)
        for token in self.session.scalars(stmt).all():
            token.revoked = True
