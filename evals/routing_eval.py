"""Router accuracy evaluation.

Runs the real supervisor prompt over ``routing_golden.jsonl`` and reports accuracy
plus a confusion matrix. This is the cheapest, highest-signal eval to run in CI: a
routing regression silently breaks the whole desk.

Run:  python -m evals.routing_eval
Cheap/fast run (14-case curated subset): python -m evals.routing_eval --golden routing_golden_sample.jsonl
Or cap any golden file to the first N cases: python -m evals.routing_eval --limit 10
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.guardrails import check_input
from app.core.logging import configure_logging, get_logger
from app.core.prompts import ROUTER_SYSTEM
from app.schemas.chat import Route, RouterDecision
from app.services.llm import llm_service
from evals.common import load_jsonl, save_report

configure_logging()
logger = get_logger(__name__)


async def _predict(message: str) -> str:
    # Mirror the supervisor's guardrail short-circuits so the eval matches prod.
    guard = check_input(message)
    if not guard.allowed:
        return Route.OUT_OF_SCOPE.value
    if "self_harm_signal" in guard.flags:
        return Route.ESCALATE.value
    try:
        decision: RouterDecision = await llm_service.structured(
            [SystemMessage(content=ROUTER_SYSTEM), HumanMessage(content=message)],
            schema=RouterDecision,
        )
        return decision.route.value
    except Exception as exc:  # noqa: BLE001
        logger.warning("router_predict_failed", error=str(exc))
        return Route.TRACK.value  # matches supervisor_node's own fail-safe route


async def main(golden_file: str = "routing_golden.jsonl", limit: int | None = None) -> dict:
    rows = load_jsonl(golden_file)
    if limit is not None:
        rows = rows[:limit]
    correct = 0
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    details = []
    for row in rows:
        pred = await _predict(row["message"])
        exp = row["expected_route"]
        confusion[exp][pred] += 1
        hit = pred == exp
        correct += int(hit)
        details.append({"message": row["message"][:60], "expected": exp, "predicted": pred, "correct": hit})

    accuracy = correct / max(len(rows), 1)
    report = {
        "suite": "routing",
        "timestamp": datetime.now(UTC).isoformat(),
        "golden_file": golden_file,
        "n": len(rows),
        "accuracy": round(accuracy, 3),
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
        "details": details,
    }
    save_report("routing_latest.json", report)
    logger.info("routing_eval_done", accuracy=report["accuracy"])
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the routing-accuracy eval.")
    parser.add_argument(
        "--golden",
        default="routing_golden.jsonl",
        help="Golden dataset filename under evals/golden/ (default: routing_golden.jsonl, "
        "the full set). Use routing_golden_sample.jsonl for a cheap 14-case run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only evaluate the first N cases from --golden (cheaper/faster runs).",
    )
    args = parser.parse_args()
    asyncio.run(main(golden_file=args.golden, limit=args.limit))
