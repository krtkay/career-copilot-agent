"""HTTP middleware: request id binding + Prometheus timing."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.metrics import REQUEST_COUNT, REQUEST_LATENCY


def _route_label(request: Request) -> str:
    """Low-cardinality label: the matched route template, else the raw path."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


class ContextLoggingMiddleware(BaseHTTPMiddleware):
    """Bind a request id to structlog contextvars and record latency."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start

        # After call_next the route template is available in scope.
        label = _route_label(request)
        REQUEST_LATENCY.labels(request.method, label).observe(elapsed)
        REQUEST_COUNT.labels(request.method, label, response.status_code).inc()
        response.headers["x-request-id"] = request_id
        return response
