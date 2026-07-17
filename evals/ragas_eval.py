"""RAG quality evaluation with RAGAS.

For every question in ``rag_golden.jsonl`` we run the *real* hybrid retriever, build
an answer with the *real* LLM service, then score the (question, answer, contexts,
ground_truth) tuple with RAGAS metrics:

* faithfulness        — is the answer grounded in the retrieved contexts?
* answer_relevancy    — does the answer address the question?
* context_precision   — are the retrieved contexts relevant (low noise)?
* context_recall      — did retrieval surface everything needed vs ground truth?

RAGAS itself needs an LLM + embeddings; we point it at the same free provider and
local fastembed model the app uses, so evaluation costs nothing extra.

Run:  python -m evals.ragas_eval
Cheap/fast run (10-question curated subset):
      python -m evals.ragas_eval --golden rag_golden_sample.jsonl
Or cap any golden file to the first N questions:
      python -m evals.ragas_eval --limit 10
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.prompts import KNOWLEDGE_SYSTEM
from app.services.database import AsyncSessionLocal
from app.services.llm import llm_service
from app.services.retrieval import hybrid_retriever
from evals.common import load_jsonl, save_report

configure_logging()
logger = get_logger(__name__)


async def _answer(question: str) -> tuple[str, list[str]]:
    async with AsyncSessionLocal() as session:
        chunks = await hybrid_retriever.retrieve(session, question)
    contexts = [c.content for c in chunks]
    if not contexts:
        return "I don't have that information.", []
    ctx_block = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1))
    prompt = f"Context:\n{ctx_block}\n\nQuestion: {question}\nAnswer with citations."
    answer = await llm_service.chat(
        [SystemMessage(content=KNOWLEDGE_SYSTEM), HumanMessage(content=prompt)]
    )
    return answer, contexts


async def build_dataset(golden_file: str = "rag_golden.jsonl", limit: int | None = None) -> list[dict]:
    rows = load_jsonl(golden_file)
    if limit is not None:
        rows = rows[:limit]
    samples = []
    for row in rows:
        answer, contexts = await _answer(row["question"])
        samples.append(
            {
                "user_input": row["question"],
                "response": answer,
                "retrieved_contexts": contexts,
                "reference": row["ground_truth"],
            }
        )
        logger.info("rag_sample_built", q=row["question"][:48])
    return samples


def _score_with_ragas(samples: list[dict]) -> dict:
    """Score with RAGAS if installed; otherwise fall back to a lexical proxy."""
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from langchain_openai import ChatOpenAI

        provider = settings.llm_providers()[0]
        eval_llm = LangchainLLMWrapper(
            ChatOpenAI(
                model=provider.model,
                base_url=provider.base_url,
                api_key=provider.api_key.get_secret_value(),
                temperature=0,
            )
        )

        # Wrap the local fastembed model behind the LangChain embeddings interface.
        from langchain_core.embeddings import Embeddings

        from app.services.embeddings import embedding_service

        class _LocalEmb(Embeddings):
            def embed_documents(self, texts):
                return embedding_service.embed_documents(list(texts))

            def embed_query(self, text):
                return embedding_service.embed_query(text)

        eval_emb = LangchainEmbeddingsWrapper(_LocalEmb())

        ds = Dataset.from_list(samples)
        result = evaluate(
            ds,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
            llm=eval_llm,
            embeddings=eval_emb,
        )
        # `EvaluationResult.scores` is a per-sample list of {metric_name: score} dicts
        # (this ragas version has no dict-like aggregate on the result itself) —
        # average each metric across samples ourselves.
        per_sample = result.scores
        if not per_sample:
            scores = {}
        else:
            keys = per_sample[0].keys()
            scores = {k: float(sum(s[k] for s in per_sample) / len(per_sample)) for k in keys}
        return {"engine": "ragas", "scores": scores}
    except Exception as exc:  # noqa: BLE001
        logger.warning("ragas_unavailable_using_proxy", error=str(exc))
        return _lexical_proxy(samples)


def _lexical_proxy(samples: list[dict]) -> dict:
    """Cheap, dependency-free stand-in so evals always produce a number."""
    from app.core.guardrails.output_guard import groundedness_score

    faith, recall = [], []
    for s in samples:
        faith.append(groundedness_score(s["response"], s["retrieved_contexts"]))
        recall.append(groundedness_score(s["reference"], s["retrieved_contexts"]))
    n = max(len(samples), 1)
    return {
        "engine": "lexical_proxy",
        "scores": {
            "faithfulness_proxy": sum(faith) / n,
            "context_recall_proxy": sum(recall) / n,
        },
    }


async def main(golden_file: str = "rag_golden.jsonl", limit: int | None = None) -> dict:
    samples = await build_dataset(golden_file, limit)
    scored = _score_with_ragas(samples)
    report = {
        "suite": "ragas",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "golden_file": golden_file,
        "n_samples": len(samples),
        **scored,
    }
    path = save_report("ragas_latest.json", report)
    logger.info("ragas_report_written", path=str(path), scores=scored["scores"])
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the RAGAS RAG-quality eval.")
    parser.add_argument(
        "--golden",
        default="rag_golden.jsonl",
        help="Golden dataset filename under evals/golden/ (default: rag_golden.jsonl, "
        "the full set). Use rag_golden_sample.jsonl for a cheap 10-question run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only evaluate the first N questions from --golden (cheaper/faster runs).",
    )
    args = parser.parse_args()
    asyncio.run(main(golden_file=args.golden, limit=args.limit))
