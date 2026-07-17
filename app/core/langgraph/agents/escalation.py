"""Escalation + simple conversational nodes.

The escalation node demonstrates **human-in-the-loop** with LangGraph's ``interrupt``:
the graph pauses, surfaces a hand-off summary to the caller, and can be resumed once
a human has acted (see ``docs/architecture.md`` for the resume flow). To keep the
default HTTP path non-blocking, we catch the interrupt and mark ``needs_human`` so the
API can return immediately while the ticket sits in ``pending_human``.
"""

from __future__ import annotations

from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.config import settings
from app.core.langgraph.agents.common import conversation_history, last_user_text
from app.core.langgraph.state import SupportState
from app.core.logging import get_logger
from app.core.prompts import (
    ESCALATION_SYSTEM,
    OUT_OF_SCOPE_MESSAGE,
    SMALLTALK_SYSTEM,
)
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.services.database import AsyncSessionLocal
from app.services.llm import llm_service

logger = get_logger(__name__)


async def escalation_node(state: SupportState) -> dict:
    convo = conversation_history(state)
    try:
        handoff = await llm_service.chat(
            [SystemMessage(content=ESCALATION_SYSTEM), HumanMessage(content=convo)]
        )
    except Exception:  # noqa: BLE001
        handoff = (
            "Thanks for your patience — I'm connecting you with a human specialist "
            "who will follow up shortly."
        )

    # Persist a high-priority ticket flagged for a human.
    user_id = state.get("user_id")
    ticket = Ticket(
        user_id=UUID(user_id) if user_id else None,
        session_id=state.get("session_id", "unknown"),
        category="escalation",
        priority=TicketPriority.HIGH,
        status=TicketStatus.PENDING_HUMAN,
        subject="Escalation to human agent",
        summary=convo[:500],
        assigned_to=settings.escalation_email,
    )
    async with AsyncSessionLocal() as session:
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

    logger.info("escalated_to_human", ticket_id=str(ticket.id))
    return {
        "answer": handoff,
        "needs_human": True,
        "ticket": {"id": str(ticket.id), "status": ticket.status.value},
        "messages": [AIMessage(content=handoff)],
    }


async def smalltalk_node(state: SupportState) -> dict:
    last = last_user_text(state)
    history = conversation_history(state, max_messages=4, include_current_turn=False)
    prompt = f"Recent conversation:\n{history}\n\nLatest message: {last}" if history else last
    try:
        reply = await llm_service.chat(
            [SystemMessage(content=SMALLTALK_SYSTEM), HumanMessage(content=prompt)]
        )
    except Exception:  # noqa: BLE001
        reply = "Hi! How can I help with your account, orders, or a technical issue?"
    return {"answer": reply, "messages": [AIMessage(content=reply)]}


async def out_of_scope_node(state: SupportState) -> dict:
    return {
        "answer": OUT_OF_SCOPE_MESSAGE,
        "messages": [AIMessage(content=OUT_OF_SCOPE_MESSAGE)],
    }
