# Evaluation

Evaluation is first-class here because "it works on my three test prompts" is not
an AI Engineering answer. Three suites run offline against **golden datasets** and
double as a CI quality gate.

Run everything:

```bash
make eval          # or: python -m evals.run_all
```

Outputs land in `evals/reports/` (`report.md`, `combined_latest.json`, plus a
per-suite JSON). `run_all` exits non-zero if any metric is below its threshold.

## Golden datasets (`evals/golden/`)

- `rag_golden.jsonl` — questions with a `ground_truth` answer and
  `reference_contexts`. Used to score retrieval + answer quality.
- `routing_golden.jsonl` — messages with the `expected_route`. Used to score the
  supervisor.
- `guardrail_cases.jsonl` — labelled inputs/outputs with the flag each should
  trigger (or `null` for benign traffic).

These are small on purpose (fast, free to run). Grow them as you find failures —
every production incident should become a new golden row (regression test).

## 1. RAG quality — RAGAS (`evals/ragas_eval.py`)

For each golden question we run the **real** hybrid retriever and LLM, then score
with RAGAS:

- **faithfulness** — is the answer supported by the retrieved contexts? (catches
  hallucination)
- **answer_relevancy** — does the answer actually address the question?
- **context_precision** — how much of the retrieved context is relevant? (noise)
- **context_recall** — did retrieval surface everything the ground truth needs?

RAGAS itself needs an LLM + embeddings; we point it at the **same free provider**
and **local fastembed** model, so evaluation costs nothing extra. If RAGAS isn't
installed (`pip install -e ".[evals]"`), the suite falls back to a lexical
groundedness proxy so you always get a number.

## 2. Routing accuracy (`evals/routing_eval.py`)

Runs the real supervisor prompt over the routing golden set and reports accuracy
plus a **confusion matrix** (so you can see *which* routes get confused). This is
the cheapest, highest-signal eval — a routing regression silently breaks the whole
desk.

## 3. Guardrail precision (`evals/guardrail_eval.py`)

Deterministic and instant (no LLM). Verifies injection/PII/redaction rules fire on
the cases that should trip them and stay quiet on benign traffic. Reports
precision/recall and a per-case breakdown.

## Thresholds / CI gate

Defined in `evals/run_all.py`:

```python
THRESHOLDS = {
    "routing_accuracy": 0.75,
    "guardrail_precision": 0.90,
    "faithfulness": 0.70,          # when RAGAS is installed
    "faithfulness_proxy": 0.30,    # lexical fallback
}
```

Wire `python -m evals.run_all` into CI to block merges that regress quality.

## The improvement loop

1. A user turn fails (wrong route, weak answer, missed guardrail).
2. Add it as a golden row with the correct expectation.
3. Change the prompt / retrieval / guardrail.
4. Re-run `make eval`; confirm the new row passes and nothing else regressed.
5. Commit — the golden set is now your regression suite.
