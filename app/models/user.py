"""User model — minimal auth identity for JWT sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """A support-desk end user (or agent) authenticated via JWT."""

    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    full_name: str | None = None
    is_active: bool = True
    is_agent: bool = Field(default=False, description="True for human support staff.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
