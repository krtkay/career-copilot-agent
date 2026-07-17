"""Pytest fixtures.

Unit tests run with no network and no database (they exercise pure logic and use a
fake LLM). Integration tests are marked ``integration`` and require the Docker stack
(``make docker-up``); skip them in a quick local loop with ``-m "not integration"``.
"""

from __future__ import annotations

import os

import pytest

# Force a safe test environment before any app import reads settings.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("GUARDRAILS_ENABLED", "true")


@pytest.fixture
def fake_llm(monkeypatch):
    """Patch the LLM service so tests are deterministic and offline."""
    from langchain_core.messages import AIMessage

    from app.schemas.chat import Route, RouterDecision, TriageResult
    from app.services import llm as llm_module

    class FakeLLM:
        def __init__(self):
            self.chat_response = "This is a grounded test answer based on the context [1]."
            self.chat_calls: list[list] = []
            self.structured_calls: list[tuple[list, type]] = []
            self.chat_with_tools_calls: list[list] = []
            self.has_providers = True
            # No tool_calls => job_search_node's loop exits after one step.
            self.bound_reply = AIMessage(content="Here are some jobs I found for you.")

        async def chat(self, messages):
            self.chat_calls.append(messages)
            return self.chat_response

        async def structured(self, messages, schema):
            self.structured_calls.append((messages, schema))
            if schema is RouterDecision:
                return RouterDecision(
                    route=Route.KNOWLEDGE, reason="looks like a KB question", confidence=0.9
                )
            if schema is TriageResult:
                return TriageResult(
                    category="application", priority="high", subject="Test", summary="Test summary"
                )
            raise NotImplementedError(schema)

        async def chat_with_tools(self, messages, tools):
            # Copy: job_search_node's loop mutates the same list object afterward
            # (convo.append(ai)) — snapshot it here.
            self.chat_with_tools_calls.append(list(messages))
            return self.bound_reply

    fake = FakeLLM()
    monkeypatch.setattr(llm_module, "llm_service", fake)
    # Each agent node does `from app.services.llm import llm_service`, binding its own
    # module-level name at import time — patching app.services.llm.llm_service alone
    # doesn't reach those already-bound references, so patch every consumer directly.
    from app.core.langgraph.agents import (
        draft,
        escalation,
        job_search,
        knowledge,
        supervisor,
        triage,
    )

    for module in (draft, escalation, job_search, knowledge, supervisor, triage):
        monkeypatch.setattr(module, "llm_service", fake)
    return fake
