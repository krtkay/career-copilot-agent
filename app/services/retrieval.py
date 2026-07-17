"""Hybrid retrieval: semantic (pgvector) + keyword (Postgres full-text), fused
with Reciprocal Rank Fusion (RRF).

Why hybrid?
    * **Semantic** search (dense embeddings) captures meaning and paraphrase
      ("my card was declined" ~ "payment failed") but can miss exact tokens like
      error codes, SKUs, or product names.
    * **Keyword** search (BM25-style ``ts_rank_cd`` over a ``tsvector``) nails exact
      terms and rare identifiers but misses paraphrase.
    * **RRF** combines both ranked lists without needing calibrated scores:
      ``score(d) = Σ 1 / (k + rank_i(d))``. It is robust, tuning-light, and the
      de-facto default for production hybrid search.

Both retrievers run against Postgres, so there is no separate search service to
operate.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import RETRIEVAL_HITS, RETRIEVAL_LATENCY
from app.services.embeddings import embedding_service

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_title: str
    source: str
    content: str
    # Per-retriever ranks (1-based); None if not present in that list.
    semantic_rank: int | None = None
    keyword_rank: int | None = None
    fused_score: float = 0.0
    debug: dict = field(default_factory=dict)


class HybridRetriever:
    """Runs semantic + keyword retrieval and fuses the results."""

    async def _semantic(
        self, session: AsyncSession, query: str, k: int
    ) -> list[RetrievedChunk]:
        vec = embedding_service.embed_query(query)
        # pgvector cosine distance operator is ``<=>``; smaller = closer.
        sql = text(
            """
            SELECT c.id::text AS chunk_id,
                   c.document_id::text AS document_id,
                   d.title AS document_title,
                   d.source AS source,
                   c.content AS content,
                   1 - (c.embedding <=> CAST(:qvec AS vector)) AS similarity
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id
            ORDER BY c.embedding <=> CAST(:qvec AS vector)
            LIMIT :k
            """
        )
        rows = (await session.execute(sql, {"qvec": str(vec), "k": k})).mappings().all()
        return [
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                document_title=r["document_title"],
                source=r["source"],
                content=r["content"],
                semantic_rank=i + 1,
                debug={"similarity": float(r["similarity"])},
            )
            for i, r in enumerate(rows)
        ]

    async def _keyword(
        self, session: AsyncSession, query: str, k: int
    ) -> list[RetrievedChunk]:
        # ``websearch_to_tsquery`` accepts natural language ("foo -bar \"baz\"").
        sql = text(
            """
            SELECT c.id::text AS chunk_id,
                   c.document_id::text AS document_id,
                   d.title AS document_title,
                   d.source AS source,
                   c.content AS content,
                   ts_rank_cd(c.content_tsv, q) AS rank
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id,
                 websearch_to_tsquery('english', :query) q
            WHERE c.content_tsv @@ q
            ORDER BY rank DESC
            LIMIT :k
            """
        )
        rows = (
            await session.execute(sql, {"query": query, "k": k})
        ).mappings().all()
        return [
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                document_title=r["document_title"],
                source=r["source"],
                content=r["content"],
                keyword_rank=i + 1,
                debug={"ts_rank": float(r["rank"])},
            )
            for i, r in enumerate(rows)
        ]

    @staticmethod
    def _fuse(
        semantic: list[RetrievedChunk],
        keyword: list[RetrievedChunk],
        rrf_k: int,
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Reciprocal Rank Fusion over the two ranked lists."""
        merged: dict[str, RetrievedChunk] = {}

        def _add(chunks: list[RetrievedChunk], which: str) -> None:
            for c in chunks:
                existing = merged.get(c.chunk_id)
                if existing is None:
                    merged[c.chunk_id] = c
                    existing = c
                rank = c.semantic_rank if which == "semantic" else c.keyword_rank
                if which == "semantic":
                    existing.semantic_rank = rank
                else:
                    existing.keyword_rank = rank
                existing.fused_score += 1.0 / (rrf_k + rank)
                existing.debug.update(c.debug)

        _add(semantic, "semantic")
        _add(keyword, "keyword")
        ranked = sorted(merged.values(), key=lambda c: c.fused_score, reverse=True)
        return ranked[:top_k]

    async def retrieve(
        self, session: AsyncSession, query: str, top_k: int | None = None
    ) -> list[RetrievedChunk]:
        top_k = top_k or settings.retrieval_top_k
        started = time.monotonic()
        semantic = await self._semantic(session, query, settings.retrieval_candidate_k)
        keyword = await self._keyword(session, query, settings.retrieval_candidate_k)
        fused = self._fuse(semantic, keyword, settings.rrf_k, top_k)
        elapsed = time.monotonic() - started

        RETRIEVAL_LATENCY.labels("hybrid").observe(elapsed)
        RETRIEVAL_HITS.observe(len(fused))
        logger.info(
            "hybrid_retrieval",
            query_chars=len(query),
            semantic_hits=len(semantic),
            keyword_hits=len(keyword),
            fused_hits=len(fused),
            elapsed_ms=round(elapsed * 1000, 1),
        )
        return fused


hybrid_retriever = HybridRetriever()
