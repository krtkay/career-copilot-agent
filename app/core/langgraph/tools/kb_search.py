"""Knowledge-base search tool (hybrid keyword + semantic)."""

from __future__ import annotations

from langchain_core.tools import tool

from app.services.database import AsyncSessionLocal
from app.services.retrieval import hybrid_retriever


@tool
async def search_knowledge_base(query: str, top_k: int = 5) -> str:
    """Search the career knowledge base using hybrid keyword + semantic retrieval.

    Use this to find documented career guidance about resumes and ATS, interviews and the STAR method, salary negotiation, cover letters, and job-search strategy. Returns the most relevant passages with their titles.
    """
    async with AsyncSessionLocal() as session:
        chunks = await hybrid_retriever.retrieve(session, query, top_k=top_k)
    if not chunks:
        return "No relevant knowledge-base passages found."
    return "\n\n".join(
        f"[{i}] {c.document_title}: {c.content}" for i, c in enumerate(chunks, 1)
    )
