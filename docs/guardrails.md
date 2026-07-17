# Guardrails

Guardrails are **fast, deterministic, and inline** — no extra LLM round-trip, no
heavy framework. Each check returns structured flags; the graph decides whether to
block, redact, or annotate. They never raise.

## Input guardrails (`app/core/guardrails/input_guard.py`)

Run in the supervisor before routing.

| Check | Behaviour |
| --- | --- |
| **Length** | Messages over `GUARDRAIL_MAX_INPUT_CHARS` are **blocked** (routed to `out_of_scope`). Cheap DoS/abuse protection. |
| **Prompt injection** | Heuristic patterns ("ignore previous instructions", "reveal system prompt", "DAN mode"). **Flagged** (not hard-blocked) so real user text isn't falsely rejected; the router treats flagged turns conservatively. |
| **Self-harm signal** | Flagged and **forced to `escalate`** with `needs_human=True` so a person responds with care. Never handled by the bot alone. |
| **PII in input** | Detected and flagged (`pii_in_input`) for audit; the user's own PII isn't blocked. |

## Output guardrails (`app/core/guardrails/output_guard.py`)

Run before the answer leaves a node.

| Check | Behaviour |
| --- | --- |
| **PII egress redaction** | Any PII the model echoes is replaced with `[REDACTED_<TYPE>]`. Flagged `pii_redacted`. |
| **Groundedness** | For KB answers, a lexical-overlap proxy measures how much of the answer is supported by retrieved context. Below `GUARDRAIL_MIN_GROUNDEDNESS` → flag `low_groundedness`, append an uncertainty caveat, offer a ticket. The deeper LLM-graded faithfulness score lives in the RAGAS eval (offline, where the cost is acceptable). |

## PII detection (`app/core/guardrails/pii.py`)

Regex-based baseline covering email, credit card, SSN, phone, IPv4, and
API-key-like tokens. Transparent and dependency-free. For a regulated deployment,
swap in **Microsoft Presidio** behind the same `scan_pii` / `redact_pii`
interface — no caller changes.

## Why not a full guardrails framework?

NeMo Guardrails / guardrails-ai are powerful but heavy and often add latency and
another model call. For a support desk the high-value checks are simple and
deterministic, so we keep them inline and **measure** them (see
`evals/guardrail_eval.py`) rather than trusting them blindly. The design leaves a
clean seam to add an LLM-based toxicity/topical classifier as an optional node if
a use case needs nuance.

## Tuning

All thresholds are in `app/core/config.py` (`guardrail_*`). Adjusting them changes
behaviour immediately; re-run `make eval` to confirm precision/recall hold.
