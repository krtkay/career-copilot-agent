"""Guardrail evaluation — precision on labelled safety cases.

Deterministic and instant (no LLM). Verifies that injection/PII/redaction rules fire
on the cases that should trip them and stay quiet on benign traffic.

Run:  python -m evals.guardrail_eval
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.guardrails import check_input, check_output
from app.core.logging import configure_logging, get_logger
from evals.common import load_jsonl, save_report

configure_logging()
logger = get_logger(__name__)


def _flags_for(case: dict) -> list[str]:
    if case["stage"] == "input":
        return check_input(case["text"]).flags
    return check_output(case["text"]).flags


def main() -> dict:
    rows = load_jsonl("guardrail_cases.jsonl")
    tp = fp = tn = fn = 0
    details = []
    for case in rows:
        flags = _flags_for(case)
        expected = case["expect_flag"]
        if expected is None:
            ok = len(flags) == 0
            tn += int(ok)
            fp += int(not ok)
        else:
            ok = expected in flags
            tp += int(ok)
            fn += int(not ok)
        details.append({"text": case["text"][:60], "expected": expected, "flags": flags, "ok": ok})

    denom_p = tp + fp
    denom_r = tp + fn
    report = {
        "suite": "guardrails",
        "timestamp": datetime.now(UTC).isoformat(),
        "n": len(rows),
        "precision": round(tp / denom_p, 3) if denom_p else 1.0,
        "recall": round(tp / denom_r, 3) if denom_r else 1.0,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "details": details,
    }
    save_report("guardrails_latest.json", report)
    logger.info("guardrail_eval_done", precision=report["precision"], recall=report["recall"])
    return report


if __name__ == "__main__":
    main()
