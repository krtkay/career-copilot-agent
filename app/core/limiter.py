"""Rate limiting via slowapi.

The limiter keys on the authenticated user id when available (so one noisy user
cannot exhaust another's budget) and falls back to the client IP for anonymous
routes. Per-route overrides use the ``@limiter.limit(...)`` decorator.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings


def _rate_key(request: Request) -> str:
    """Prefer the authenticated user id, else the remote address."""
    user = getattr(request.state, "user", None)
    if user and getattr(user, "id", None):
        return f"user:{user.id}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=_rate_key,
    default_limits=[settings.rate_limit_default],
    headers_enabled=True,
)
