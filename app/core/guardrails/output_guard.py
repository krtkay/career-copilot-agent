"""Output guardrails — run before the answer is returned to the user.

Two responsibilities:

1. **Groundedness** — for KB answers, verify the response is actually supported by
   retrieved context. We use a lightweight lexical-overlap proxy (token Jaccard of
   the answer against the concatenated sources). It is cheap and deterministic; the
   deeper, LLM-graded faithfulness score lives in the RAGAS eval suite where the
   extra cost is acceptable (offline). If overlap is below threshold we flag a
   possible hallucination so the graph can append a caveat or escalate.
2. **PII egress** — redact any PII the model may have echoed back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.guardrails.pii import redact_pii
from app.core.metrics import GUARDRAIL_BLOCK_COUNT

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    ["the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "is", "are", "be", "this", "that", "with", "your", "you", "it", "as", "we"]
)


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 2}


def groundedness_score(answer: str, sources: list[str]) -> float:
    """Fraction of meaningful answer tokens that appear in the sources."""
    ans = _tokens(answer)
    if not ans:
        return 1.0
    src = set()
    for s in sources:
        src |= _tokens(s)
    return len(ans & src) / len(ans)


@dataclass
class OutputGuardResult:
    answer: str
    flags: list[str] = field(default_factory=list)
    groundedness: float | None = None


def check_output(
    answer: str, sources: list[str] | None = None, *, require_grounding: bool = False
) -> OutputGuardResult:
    """Validate/sanitise an outbound answer. Never raises."""
    result = OutputGuardResult(answer=answer)
    if not settings.guardrails_enabled:
        return result

    if settings.guardrail_block_pii_output:
        redacted, categories = redact_pii(answer)
        if categories:
            result.answer = redacted
            result.flags.append("pii_redacted")
            GUARDRAIL_BLOCK_COUNT.labels("output", "pii_redacted").inc()

    if require_grounding and sources:
        score = groundedness_score(result.answer, sources)
        result.groundedness = round(score, 3)
        if score < settings.guardrail_min_groundedness:
            result.flags.append("low_groundedness")
            GUARDRAIL_BLOCK_COUNT.labels("output", "low_groundedness").inc()

    return result
