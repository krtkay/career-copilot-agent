"""Triage agent — extracts a structured ticket and persists it."""

from __future__ import annotations

from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.langgraph.agents.common import conversation_history
from app.core.langgraph.state import SupportState
from app.core.logging import get_logger
from app.core.prompts import TRIAGE_SYSTEM
from app.models.ticket import Ticket, TicketPriority
from app.schemas.chat import TriageResult
from app.services.database import AsyncSessionLocal
from app.services.llm import llm_service

logger = get_logger(__name__)


async def triage_node(state: SupportState) -> dict:
    convo = conversation_history(state)
    try:
        result: TriageResult = await llm_service.structured(
            [SystemMessage(content=TRIAGE_SYSTEM), HumanMessage(content=convo)],
            schema=TriageResult,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("triage_extraction_failed", error=str(exc))
        result = TriageResult(
            category="application",
            priority="medium",
            subject="Job search item",
            summary=convo[:280],
        )

    user_id = state.get("user_id")
    ticket = Ticket(
        user_id=UUID(user_id) if user_id else None,
        session_id=state.get("session_id", "unknown"),
        category=result.category,
        priority=TicketPriority(result.priority),
        subject=result.subject,
        summary=result.summary,
    )
    async with AsyncSessionLocal() as session:
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

    logger.info(
        "ticket_created",
        ticket_id=str(ticket.id),
        category=ticket.category,
        priority=ticket.priority.value,
    )
    answer = (
        f"Added to your tracker as **#{str(ticket.id)[:8]}** "
        f"({result.category}, {result.priority} priority): {result.subject}. "
        f"{result.summary}"
    )
    return {
        "ticket": {
            "id": str(ticket.id),
            "category": ticket.category,
            "priority": ticket.priority.value,
            "subject": ticket.subject,
        },
        "answer": answer,
        "messages": [AIMessage(content=answer)],
    }
