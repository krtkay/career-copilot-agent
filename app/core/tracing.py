"""Langfuse tracing — optional, off by default.

When ``LANGFUSE_TRACING_ENABLED=true`` and both keys are set, ``get_callbacks()``
returns a LangChain callback handler that ships the whole graph run — every routing
decision, retrieval, and LLM call — to Langfuse as a nested trace (spans, token usage,
latency, cost). We attach it once at the top-level graph invocation and LangChain/
LangGraph propagate it to every nested runnable, so no other code changes are needed.

When tracing is off or misconfigured, ``get_callbacks()`` returns ``[]``, so call sites
never branch — they always pass ``config={"callbacks": get_callbacks(), ...}``.

The handler import/constructor differs between Langfuse v2 and v3+, so we support
both — the v3-shaped branch below also covers v4 (same ``langfuse.langchain``
import path and no-arg ``CallbackHandler()``; only advanced params changed).
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _installed_version() -> str:
    try:
        return version("langfuse")
    except PackageNotFoundError:
        return "unknown"

# Bounds how long graceful shutdown waits on a Langfuse flush. The SDK's own
# flush has no timeout parameter and can block on network I/O; if the host is
# unreachable at shutdown time we'd rather drop the last few traces than stall
# the process past the orchestrator's SIGTERM grace period (Docker's default
# is 10s).
_FLUSH_TIMEOUT_S = 5.0


@lru_cache(maxsize=1)
def _handler():
    if not settings.langfuse_tracing_enabled:
        return None

    public = settings.langfuse_public_key.get_secret_value()
    secret = settings.langfuse_secret_key.get_secret_value()
    if not public or not secret:
        logger.warning("langfuse_enabled_but_keys_missing")
        return None

    host = settings.langfuse_host

    # --- Langfuse v2: keys passed straight to the callback handler ---------
    try:
        from langfuse.callback import CallbackHandler  # type: ignore

        handler = CallbackHandler(public_key=public, secret_key=secret, host=host)
        logger.info("langfuse_tracing_enabled", version="v2", host=host)
        return handler
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse_v2_init_failed", error=str(exc))

    # --- Langfuse v3/v4: configure the client, then a no-arg handler ------
    try:
        from langfuse import Langfuse  # type: ignore
        from langfuse.langchain import CallbackHandler  # type: ignore

        # Initialising the client sets the process-wide singleton the handler uses.
        Langfuse(public_key=public, secret_key=secret, host=host)
        handler = CallbackHandler()
        logger.info("langfuse_tracing_enabled", version=_installed_version(), host=host)
        return handler
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse_init_failed", error=str(exc))
        return None


def get_callbacks() -> list:
    """Return ``[handler]`` if Langfuse is configured, else ``[]``."""
    handler = _handler()
    return [handler] if handler else []


def _flush_sync() -> None:
    """Best-effort, version-aware flush. Never raises."""
    # --- Langfuse v3/v4: flush the process-wide client singleton ----------
    try:
        from langfuse import get_client  # type: ignore

        get_client().flush()
        return
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse_flush_failed", version=_installed_version(), error=str(exc))
        return

    # --- Langfuse v2: the callback handler wraps its own client -----------
    try:
        _handler().langfuse.flush()  # type: ignore[union-attr]
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse_flush_failed", version="v2", error=str(exc))


async def flush() -> None:
    """Flush buffered Langfuse events. No-op when tracing is off/misconfigured.

    Call this during graceful shutdown — the SDK batches events, and a process
    exit without a flush can drop traces for the last few in-flight requests.
    """
    if _handler() is None:
        return

    try:
        await asyncio.wait_for(asyncio.to_thread(_flush_sync), timeout=_FLUSH_TIMEOUT_S)
    except TimeoutError:
        logger.warning("langfuse_flush_timeout", timeout_s=_FLUSH_TIMEOUT_S)
