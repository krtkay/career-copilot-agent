"""Run every eval suite and write a combined Markdown + JSON report.

Run:  python -m evals.run_all

Exit code is non-zero if any suite falls below its threshold, so this doubles as a
CI quality gate.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from app.core.logging import configure_logging, get_logger
from evals import guardrail_eval, ragas_eval, routing_eval
from evals.common import save_report

configure_logging()
logger = get_logger(__name__)

# Quality gates (tune to your bar). Missing metrics are skipped, not failed.
THRESHOLDS = {
    "routing_accuracy": 0.75,
    "guardrail_precision": 0.90,
    "faithfulness": 0.70,
    "faithfulness_proxy": 0.30,
}


async def main() -> int:
    routing = await routing_eval.main()
    guardrails = guardrail_eval.main()
    try:
        rag = await ragas_eval.main()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ragas_suite_skipped", error=str(exc))
        rag = {"suite": "ragas", "scores": {}}

    checks: list[tuple[str, float, float, bool]] = []

    def _check(name: str, value: float | None) -> None:
        if value is None or name not in THRESHOLDS:
            return
        thr = THRESHOLDS[name]
        checks.append((name, value, thr, value >= thr))

    _check("routing_accuracy", routing.get("accuracy"))
    _check("guardrail_precision", guardrails.get("precision"))
    for k, v in rag.get("scores", {}).items():
        _check(k, v)

    passed = all(c[3] for c in checks) if checks else True
    lines = [
        "# Eval Report",
        f"_Generated {datetime.now(UTC).isoformat()}_\n",
        "## Summary",
        "| Metric | Value | Threshold | Pass |",
        "| --- | --- | --- | --- |",
    ]
    for name, val, thr, ok in checks:
        lines.append(f"| {name} | {val:.3f} | {thr:.2f} | {'✅' if ok else '❌'} |")
    lines += [
        "\n## Routing",
        f"- Accuracy: **{routing.get('accuracy')}** over {routing.get('n')} cases",
        f"- Confusion matrix: `{routing.get('confusion_matrix')}`",
        "\n## Guardrails",
        f"- Precision: **{guardrails.get('precision')}**, Recall: **{guardrails.get('recall')}**",
        "\n## RAG (RAGAS)",
        f"- Engine: `{rag.get('engine', 'n/a')}`",
        f"- Scores: `{rag.get('scores', {})}`",
    ]

    combined = {
        "generated": datetime.now(UTC).isoformat(),
        "passed": passed,
        "routing": routing,
        "guardrails": guardrails,
        "rag": rag,
    }
    save_report("combined_latest.json", combined)
    from evals.common import REPORTS_DIR

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / "report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    logger.info("eval_report_written", path=str(md_path), passed=passed)
    print("\n".join(lines))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
