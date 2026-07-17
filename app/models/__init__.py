"""SQLModel ORM models.

Importing this package registers every table on ``SQLModel.metadata`` so that
``create_all`` and Alembic autogenerate can see them.
"""

from app.models.kb import KBChunk, KBDocument
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import User

__all__ = [
    "User",
    "KBDocument",
    "KBChunk",
    "Ticket",
    "TicketStatus",
    "TicketPriority",
]
