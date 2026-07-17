"""Input guardrails — run before the query reaches the agent graph."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.guardrails.pii import scan_pii
from app.core.metrics import GUARDRAIL_BLOCK_COUNT

# Heuristic prompt-injection / jailbreak markers. Deliberately conservative:
# these *flag* a turn for logging and stricter grounding, and only *block* on the
# most explicit override attempts, to avoid false positives on real user text.
_INJECTION_PATTERNS = [
    re.compile(r"ignore (all|any|the) (previous|prior|above) instructions", re.I),
    re.compile(r"disregard (your|the) (system|previous) prompt", re.I),
    re.compile(r"you are now (a|an|in) .{0,40}(dan|developer|jailbreak) mode", re.I),
    re.compile(r"reveal (your|the) (system prompt|instructions|hidden)", re.I),
    re.compile(r"pretend (you|to) (are|be) (not|un).{0,20}(restricted|filtered)", re.I),
]

# Obvious abuse/toxicity keyword screen (kept minimal; an LLM classifier can be
# layered on top if you need nuance — see docs/guardrails.md).
_ABUSE_PATTERNS = [
    re.compile(r"\b(kill|hurt|harm) (yourself|myself)\b", re.I),
]


@dataclass
class InputGuardResult:
    allowed: bool = True
    block_reason: str | None = None
    flags: list[str] = field(default_factory=list)
    pii_categories: list[str] = field(default_factory=list)


def check_input(text: str) -> InputGuardResult:
    """Validate an inbound user message. Never raises."""
    result = InputGuardResult()
    if not settings.guardrails_enabled:
        return result

    if len(text) > settings.guardrail_max_input_chars:
        result.allowed = False
        result.block_reason = "input_too_long"
        result.flags.append("input_too_long")
        GUARDRAIL_BLOCK_COUNT.labels("input", "length").inc()
        return result

    for pat in _ABUSE_PATTERNS:
        if pat.search(text):
            # Do not block — this may be a user in distress. Flag for the
            # escalation path so a human can respond with care.
            result.flags.append("self_harm_signal")
            GUARDRAIL_BLOCK_COUNT.labels("input", "self_harm_signal").inc()

    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            result.flags.append("prompt_injection")
            GUARDRAIL_BLOCK_COUNT.labels("input", "prompt_injection").inc()
            break

    pii = scan_pii(text)
    if pii:
        result.pii_categories = pii
        result.flags.append("pii_in_input")

    return result
