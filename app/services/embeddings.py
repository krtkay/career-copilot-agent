"""Embedding service — local, free, CPU-friendly via fastembed (ONNX).

Using ``fastembed`` with ``BAAI/bge-small-en-v1.5`` (384-dim) keeps the whole
project free and light: no embedding API bills, no GPU, ~130 MB model that runs
comfortably on a laptop. The dimension here **must** match
``settings.embedding_dim`` and the pgvector column width.

The model is lazily loaded once and reused (it is thread-safe for inference).
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _model():
    # Imported lazily so importing this module (e.g. in tests) is cheap.
    from fastembed import TextEmbedding

    logger.info("loading_embedding_model", model=settings.embedding_model)
    return TextEmbedding(model_name=settings.embedding_model)


class EmbeddingService:
    """Encodes text into dense vectors for semantic search."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in _model().embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        # bge models benefit from a query instruction prefix for retrieval.
        prefixed = f"Represent this sentence for searching relevant passages: {text}"
        return next(iter(_model().query_embed([prefixed]))).tolist()


embedding_service = EmbeddingService()
