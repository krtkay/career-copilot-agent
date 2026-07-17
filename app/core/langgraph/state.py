"""Shared LangGraph state for the support-desk graph.

The state flows through every node. LangGraph merges ``messages`` via the
``add_messages`` reducer (append semantics); all other keys are last-write-wins.
"""

from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class SupportState(TypedDict, total=False):
    # Conversation (checkpointed per thread/session).
    messages: Annotated[list, add_messages]

    # Request context.
    session_id: str
    user_id: str | None

    # Routing.
    route: str
    route_reason: str
    route_confidence: float

    # Retrieval / grounding (knowledge path).
    retrieved: list[dict[str, Any]]
    citations: list[dict[str, Any]]

    # Triage path.
    ticket: dict[str, Any] | None

    # Guardrails.
    guard_input_flags: list[str]
    guard_output_flags: list[str]
    blocked: bool

    # Human-in-the-loop.
    needs_human: bool

    # Final answer surfaced to the API.
    answer: str
