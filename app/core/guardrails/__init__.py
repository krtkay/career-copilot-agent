"""Guardrails: deterministic input/output safety checks.

The design keeps guardrails **fast, deterministic, and dependency-light** so they
run inline on every turn without adding an LLM round-trip or a heavy framework.
Each check returns structured flags rather than raising, so the graph can decide
whether to block, redact, or annotate.
"""

from app.core.guardrails.input_guard import check_input
from app.core.guardrails.output_guard import check_output
from app.core.guardrails.pii import redact_pii, scan_pii

__all__ = ["check_input", "check_output", "scan_pii", "redact_pii"]
