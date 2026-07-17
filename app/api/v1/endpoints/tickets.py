"""Ticket endpoints — lets human agents list what the desk has escalated."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.models.ticket import Ticket, TicketStatus
from app.services.database import get_session

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("")
async def list_tickets(
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    limit: int = 50,
) -> list[dict]:
    if not user.is_agent:
        raise HTTPException(403, "Only support agents can list tickets.")
    stmt = select(Ticket).order_by(Ticket.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Ticket.status == status_filter)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(t.id),
            "category": t.category,
            "priority": t.priority.value,
            "status": t.status.value,
            "subject": t.subject,
            "summary": t.summary,
            "created_at": t.created_at.isoformat(),
        }
        for t in rows
    ]
