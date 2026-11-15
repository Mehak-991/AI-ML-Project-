import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """Platform user for authentication and role-based access control."""

    __tablename__ = "users"
    __table_args__ = (
        # Roles are defined in app.core.permissions.Role. The database refuses anything else,
        # so a bug or a crafted write can never store an unknown (or escalated) role.
        CheckConstraint("role IN ('user', 'admin', 'super_admin')", name="role_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(
        String(32), default="user", server_default="user", nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Embedded in access tokens as "ver". Bumped on password change, role change and
    # deactivation so previously issued access tokens stop working immediately.
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(TimestampMixin, Base):
    """Cryptographically random refresh tokens for JWT session renewal."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
