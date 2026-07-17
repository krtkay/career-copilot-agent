"""Prometheus metrics.

These counters/histograms are scraped at ``/metrics`` and surfaced in the bundled
Grafana dashboard. They give you the operational signals an interviewer expects:
request latency, LLM latency + fallback rate, retrieval quality, guardrail blocks,
and per-route agent traffic.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# --- HTTP ---------------------------------------------------------------
REQUEST_COUNT = Counter(
    "app_http_requests_total",
    "Total HTTP requests.",
    labelnames=("method", "path", "status"),
)
REQUEST_LATENCY = Histogram(
    "app_http_request_duration_seconds",
    "HTTP request latency.",
    labelnames=("method", "path"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

# --- Agent routing ------------------------------------------------------
AGENT_ROUTE_COUNT = Counter(
    "agent_route_total",
    "Number of times the supervisor routed to each specialist agent.",
    labelnames=("route",),
)

# --- LLM ----------------------------------------------------------------
LLM_CALL_LATENCY = Histogram(
    "llm_call_duration_seconds",
    "LLM call latency by provider.",
    labelnames=("provider", "outcome"),
    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32, 60),
)
LLM_FALLBACK_COUNT = Counter(
    "llm_fallback_total",
    "Number of times the LLM service fell back to a secondary provider.",
    labelnames=("from_provider", "to_provider"),
)

# --- Retrieval ----------------------------------------------------------
RETRIEVAL_LATENCY = Histogram(
    "retrieval_duration_seconds",
    "Hybrid retrieval latency.",
    labelnames=("strategy",),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
RETRIEVAL_HITS = Histogram(
    "retrieval_hits",
    "Number of documents returned by retrieval.",
    buckets=(0, 1, 2, 3, 5, 8, 13),
)

# --- Guardrails ---------------------------------------------------------
GUARDRAIL_BLOCK_COUNT = Counter(
    "guardrail_block_total",
    "Guardrail triggers.",
    labelnames=("stage", "rule"),
)
