"""Unit tests for retrieval fusion and text chunking."""

from __future__ import annotations

from app.services.retrieval import HybridRetriever, RetrievedChunk
from app.utils.chunking import chunk_text


def _chunk(cid: str, semantic=None, keyword=None):
    return RetrievedChunk(
        chunk_id=cid,
        document_id="d",
        document_title="t",
        source="s",
        content="c",
        semantic_rank=semantic,
        keyword_rank=keyword,
    )


def test_rrf_rewards_documents_in_both_lists():
    semantic = [_chunk("a", semantic=1), _chunk("b", semantic=2)]
    keyword = [_chunk("b", keyword=1), _chunk("c", keyword=2)]
    fused = HybridRetriever._fuse(semantic, keyword, rrf_k=60, top_k=3)
    # 'b' appears in both lists so it should rank first.
    assert fused[0].chunk_id == "b"
    assert {c.chunk_id for c in fused} == {"a", "b", "c"}


def test_rrf_respects_top_k():
    semantic = [_chunk(str(i), semantic=i + 1) for i in range(10)]
    fused = HybridRetriever._fuse(semantic, [], rrf_k=60, top_k=3)
    assert len(fused) == 3


def test_chunk_text_produces_reasonable_chunks():
    text = "\n\n".join(f"Paragraph number {i} with some content." for i in range(20))
    chunks = chunk_text(text, chunk_size=200, overlap=30)
    assert len(chunks) > 1
    assert all(len(c) <= 400 for c in chunks)


def test_chunk_text_handles_short_input():
    chunks = chunk_text("Just one short paragraph.")
    assert chunks == ["Just one short paragraph."]
