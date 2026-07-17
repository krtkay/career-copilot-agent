"""Knowledge agent — hybrid RAG with grounded, cited answers."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.guardrails import check_output
from app.core.langgraph.agents.common import conversation_history, last_user_text
from app.core.langgraph.state import SupportState
from app.core.logging import get_logger
from app.core.prompts import KNOWLEDGE_SYSTEM
from app.services.database import AsyncSessionLocal
from app.services.llm import llm_service
from app.services.retrieval import hybrid_retriever

logger = get_logger(__name__)


def _format_context(chunks) -> tuple[str, list[dict]]:
    blocks, citations = [], []
    for i, c in enumerate(chunks, start=1):
        blocks.append(f"[{i}] (from '{c.document_title}')\n{c.content}")
        citations.append(
            {
                "chunk_id": c.chunk_id,
                "document_title": c.document_title,
                "source": c.source,
                "snippet": c.content[:240],
                "score": round(c.fused_score, 4),
            }
        )
    return "\n\n".join(blocks), citations


async def knowledge_node(state: SupportState) -> dict:
    query = last_user_text(state)

    async with AsyncSessionLocal() as session:
        chunks = await hybrid_retriever.retrieve(session, query)

    if not chunks:
        answer = (
            "I couldn't find anything about that in our help centre. "
            "Would you like me to open a ticket so a specialist can look into it?"
        )
        return {
            "answer": answer,
            "citations": [],
            "retrieved": [],
            "messages": [AIMessage(content=answer)],
        }

    context, citations = _format_context(chunks)
    history = conversation_history(state, max_messages=6, include_current_turn=False)

    prompt_parts = []
    if history:
        prompt_parts.append(
            "Recent conversation (for context ONLY, to understand what the user is "
            "referring to — e.g. pronouns or a topic named earlier; it is NOT a "
            "source of facts and must never be used to answer):\n" + history
        )
    prompt_parts.append(f"Context passages:\n{context}")
    prompt_parts.append(
        f"User question: {query}\n\n"
        "Answer using only the context passages above and cite with [n]. If the "
        "conversation above helps you understand what the question refers to, use "
        "it only for that — the context passages remain your only source of facts."
    )
    prompt = "\n\n".join(prompt_parts)

    raw = await llm_service.chat(
        [SystemMessage(content=KNOWLEDGE_SYSTEM), HumanMessage(content=prompt)]
    )

    guarded = check_output(
        raw, sources=[c.content for c in chunks], require_grounding=True
    )
    answer = guarded.answer
    if "low_groundedness" in guarded.flags:
        answer += (
            "\n\n_Note: I'm not fully certain this is covered in our help centre. "
            "I can open a ticket if this doesn't resolve your issue._"
        )
        logger.info("low_groundedness_answer", groundedness=guarded.groundedness)

    return {
        "answer": answer,
        "citations": citations,
        "retrieved": [c.__dict__ for c in chunks],
        "guard_output_flags": guarded.flags,
        "messages": [AIMessage(content=answer)],
    }
