"""Shared helpers for building LLM prompts from SupportState.

Every node needs some view of ``state["messages"]``: either just the latest
user turn, or a short rolling window of prior conversation. Centralizing both
here keeps formatting identical everywhere and read-only (nodes return partial
state dicts, never mutate the incoming state).
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.core.langgraph.state import SupportState


def last_user_text(state: SupportState) -> str:
    """Return the most recent HumanMessage's content, or "" if none exists."""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def conversation_history(
    state: SupportState,
    *,
    max_messages: int = 8,
    include_current_turn: bool = True,
) -> str:
    """Render the last ``max_messages`` turns as "User: ..."/"Assistant: ..." lines.

    ``include_current_turn=False`` drops the trailing HumanMessage — for
    callers that already surface the current turn separately (via
    ``last_user_text``), so it isn't duplicated in the prompt.
    """
    messages = state.get("messages", [])
    if not include_current_turn and messages and isinstance(messages[-1], HumanMessage):
        messages = messages[:-1]
    parts = []
    for msg in messages:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        parts.append(f"{role}: {content}")
    return "\n".join(parts[-max_messages:])
