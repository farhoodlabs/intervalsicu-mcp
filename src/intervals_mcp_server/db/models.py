"""
SQLAlchemy models for the multi-tenant user store.

One row per Authentik subject. Intervals.icu credentials are optional (a user
exists after their first login but before they add credentials) and the API key
is stored encrypted (``api_key_enc``), never in plaintext. ``enabled`` is the
admin-approval gate — new users are created disabled.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, LargeBinary, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class User(Base):
    """A registered user and their (optional, encrypted) Intervals.icu credentials."""

    __tablename__ = "users"

    sub: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    athlete_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def has_credentials(self) -> bool:
        """True when the user has both an athlete id and an encrypted API key."""
        return bool(self.athlete_id and self.api_key_enc)
