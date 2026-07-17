"""Supervisor (router) node.

Runs the input guardrail, then asks the LLM for a *structured* routing decision.
On any failure it fails safe to the ``triage`` route (a human-reviewable ticket)
rather than dropping the user's request.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.guardrails import check_input
from app.core.langgraph.agents.common import last_user_text
from app.core.langgraph.state import SupportState
from app.core.logging import get_logger
from app.core.metrics import AGENT_ROUTE_COUNT
from app.core.prompts import ROUTER_SYSTEM
from app.schemas.chat import Route, RouterDecision
from app.services.llm import llm_service

logger = get_logger(__name__)


async def supervisor_node(state: SupportState) -> dict:
    user_text = last_user_text(state)

    guard = check_input(user_text)
    updates: dict = {"guard_input_flags": guard.flags}

    if not guard.allowed:
        updates.update(
            route=Route.OUT_OF_SCOPE.value,
            blocked=True,
            answer="Your message couldn't be processed. Please shorten it and try again.",
        )
        AGENT_ROUTE_COUNT.labels("blocked").inc()
        return updates

    # A self-harm signal always goes to a human, regardless of the LLM's opinion.
    if "self_harm_signal" in guard.flags:
        updates.update(
            route=Route.ESCALATE.value, route_reason="safety_signal", needs_human=True
        )
        AGENT_ROUTE_COUNT.labels("escalate").inc()
        return updates

    try:
        decision: RouterDecision = await llm_service.structured(
            [SystemMessage(content=ROUTER_SYSTEM), HumanMessage(content=user_text)],
            schema=RouterDecision,
        )
        route = decision.route.value
        updates.update(
            route=route,
            route_reason=decision.reason,
            route_confidence=decision.confidence,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("router_failed_failsafe_triage", error=str(exc))
        updates.update(route=Route.TRACK.value, route_reason="router_error")
        route = Route.TRACK.value

    AGENT_ROUTE_COUNT.labels(route).inc()
    logger.info("routed", route=route, confidence=updates.get("route_confidence"))
    return updates
