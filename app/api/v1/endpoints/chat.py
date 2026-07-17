"""Chat endpoint — the main entrypoint into the multi-agent graph."""

from __future__ import annotations

from uuid import uuid4

import structlog
from fastapi import APIRouter, Request, Response
from langchain_core.messages import HumanMessage

from app.api.deps import CurrentUserDep
from app.core.langgraph.graph import graph_manager
from app.core.limiter import limiter
from app.core.logging import get_logger
from app.core.tracing import get_callbacks
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Citation,
    GuardrailReport,
    Route,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = get_logger(__name__)


@router.post("", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(
    request: Request,  # required by slowapi
    response: Response,  # required by slowapi to inject rate-limit headers
    body: ChatRequest,
    user: CurrentUserDep,
) -> ChatResponse:
    """Send a message; the supervisor routes it to the right specialist agent."""
    session_id = body.session_id or str(uuid4())
    log = logger.bind(session_id=session_id, user_id=user.id)
    log.info("chat_request", chars=len(body.message))

    config = {
        "configurable": {"thread_id": session_id},
        # Langfuse tracing (no-op when disabled). Attaching here traces the whole
        # graph run — routing, retrieval, and every LLM call — as one nested trace,
        # grouped by session and user in the Langfuse UI.
        "callbacks": get_callbacks(),
        "metadata": {
            "langfuse_session_id": session_id,
            "langfuse_user_id": user.id,
            "route_hint": "chat",
            # Joins a trace back to the structlog line / x-request-id response
            # header for this same request (bound in ContextLoggingMiddleware).
            "request_id": structlog.contextvars.get_contextvars().get("request_id"),
        },
    }
    initial = {
        "messages": [HumanMessage(content=body.message)],
        "session_id": session_id,
        "user_id": user.id,
    }

    final = await graph_manager.graph.ainvoke(initial, config=config)

    citations = [Citation(**c) for c in final.get("citations", [])]
    ticket = final.get("ticket") or {}
    report = GuardrailReport(
        input_flags=final.get("guard_input_flags", []),
        output_flags=final.get("guard_output_flags", []),
        blocked=final.get("blocked", False),
    )
    log.info("chat_response", route=final.get("route"), flags=report.output_flags)

    return ChatResponse(
        session_id=session_id,
        route=Route(final.get("route", Route.TRACK.value)),
        answer=final.get("answer", ""),
        citations=citations,
        ticket_id=ticket.get("id"),
        needs_human=final.get("needs_human", False),
        guardrails=report,
    )
