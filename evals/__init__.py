"""Offline evaluation suite.

Three complementary layers, mirroring what you'd defend in an interview:

* ``ragas_eval``     — RAG answer quality (faithfulness, answer relevancy, context
  precision/recall) against a golden dataset.
* ``routing_eval``   — supervisor routing accuracy + confusion matrix.
* ``guardrail_eval`` — precision/recall of the safety guardrails on labelled cases.

``run_all`` executes everything and writes a timestamped JSON + Markdown report to
``evals/reports/`` so you can track regressions over time (and wire it into CI).
"""
