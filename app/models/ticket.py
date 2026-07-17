"""Support ticket model — produced by the triage agent."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class TicketStatus(str, Enum):
    OPEN = "open"
    PENDING_HUMAN = "pending_human"
    RESOLVED = "resolved"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Ticket(SQLModel, table=True):
    """A triaged support ticket."""

    __tablename__ = "tickets"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    session_id: str = Field(index=True)
    category: str = Field(default="general", index=True)
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM)
    status: TicketStatus = Field(default=TicketStatus.OPEN, index=True)
    subject: str
    summary: str
    assigned_to: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
