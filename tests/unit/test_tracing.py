"""Unit tests for Langfuse tracing helpers."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.core import tracing
from app.core.config import settings


@pytest.fixture(autouse=True)
def _clear_handler_cache():
    """`_handler()` is `@lru_cache`d and reads the module-level `settings`
    singleton, so a prior test's cached result would otherwise leak into the
    next one."""
    tracing._handler.cache_clear()
    yield
    tracing._handler.cache_clear()


def test_get_callbacks_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_tracing_enabled", False)
    assert tracing.get_callbacks() == []


def test_get_callbacks_empty_when_keys_missing(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_tracing_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", SecretStr(""))
    monkeypatch.setattr(settings, "langfuse_secret_key", SecretStr(""))
    assert tracing.get_callbacks() == []


async def test_flush_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_tracing_enabled", False)
    await tracing.flush()  # must not raise
