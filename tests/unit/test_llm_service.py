"""Unit tests for LLMService's provider fallback (chat/structured/chat_with_tools)."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from pydantic import SecretStr

from app.core.config import LLMProviderConfig
from app.schemas.chat import Route, RouterDecision
from app.services.llm import AllProvidersFailedError, LLMService


class _FakeClient:
    """A single test double covering all three runnable shapes LLMService uses."""

    def __init__(self, response=None, exc=None, fail_times=0):
        self.response = response
        self.exc = exc
        self.fail_times = fail_times
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        if self.fail_times and self.calls <= self.fail_times:
            raise RuntimeError("transient failure")
        if self.exc is not None:
            raise self.exc
        return self.response

    def with_structured_output(self, schema):
        return self

    def bind_tools(self, tools):
        return self


def _provider(name: str, priority: int) -> LLMProviderConfig:
    return LLMProviderConfig(
        name=name,
        model="m",
        base_url="http://example.invalid/v1",
        api_key=SecretStr("k"),
        priority=priority,
    )


def _service(*names: str) -> LLMService:
    return LLMService(providers=[_provider(n, i + 1) for i, n in enumerate(names)])


async def test_chat_falls_back_to_secondary_on_primary_failure():
    service = _service("p1", "p2")
    service._clients["p1"] = _FakeClient(exc=RuntimeError("down"))
    service._clients["p2"] = _FakeClient(response=AIMessage(content="secondary answer"))

    result = await service.chat([])
    assert result == "secondary answer"


async def test_structured_falls_back_to_secondary_on_primary_failure():
    service = _service("p1", "p2")
    service._clients["p1"] = _FakeClient(exc=RuntimeError("down"))
    decision = RouterDecision(route=Route.KNOWLEDGE, reason="r", confidence=0.5)
    service._clients["p2"] = _FakeClient(response=decision)

    result = await service.structured([], schema=RouterDecision)
    assert result is decision


async def test_chat_with_tools_falls_back_to_secondary_on_primary_failure():
    service = _service("p1", "p2")
    service._clients["p1"] = _FakeClient(exc=RuntimeError("down"))
    reply = AIMessage(content="from secondary")
    service._clients["p2"] = _FakeClient(response=reply)

    result = await service.chat_with_tools([], tools=[])
    assert result is reply


async def test_all_providers_failed_raises_for_chat_with_tools():
    service = _service("p1", "p2")
    service._clients["p1"] = _FakeClient(exc=RuntimeError("down"))
    service._clients["p2"] = _FakeClient(exc=RuntimeError("also down"))

    with pytest.raises(AllProvidersFailedError):
        await service.chat_with_tools([], tools=[])


async def test_all_providers_failed_raises_for_chat():
    service = _service("p1", "p2")
    service._clients["p1"] = _FakeClient(exc=RuntimeError("down"))
    service._clients["p2"] = _FakeClient(exc=RuntimeError("also down"))

    with pytest.raises(AllProvidersFailedError):
        await service.chat([])


async def test_call_one_retries_before_falling_back():
    """A primary that fails once then succeeds should never reach the secondary."""
    service = _service("p1", "p2")
    service._clients["p1"] = _FakeClient(
        fail_times=1, response=AIMessage(content="primary recovered")
    )
    service._clients["p2"] = _FakeClient(response=AIMessage(content="should not be used"))

    result = await service.chat_with_tools([], tools=[])
    assert result.content == "primary recovered"
    assert service._clients["p2"].calls == 0


def test_has_providers_property():
    assert _service("p1").has_providers is True
    assert LLMService(providers=[]).has_providers is False


async def test_no_providers_configured_raises_immediately():
    service = LLMService(providers=[])
    with pytest.raises(AllProvidersFailedError):
        await service.chat([])
    with pytest.raises(AllProvidersFailedError):
        await service.structured([], schema=RouterDecision)
    with pytest.raises(AllProvidersFailedError):
        await service.chat_with_tools([], tools=[])
