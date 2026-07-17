"""Draft agent — writes a career document (cover letter, resume bullets, outreach).

This is the copilot's "deliverable" agent: it turns a request into a finished piece of
writing the user can copy and use. It pulls relevant best-practice context from the KB
(so the writing follows the same advice the knowledge agent gives) and then drafts.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.guardrails import check_output
from app.core.langgraph.agents.common import conversation_history, last_user_text
from app.core.langgraph.state import SupportState
from app.core.logging import get_logger
from app.core.prompts import DRAFT_SYSTEM
from app.services.database import AsyncSessionLocal
from app.services.llm import llm_service
from app.services.retrieval import hybrid_retriever

logger = get_logger(__name__)


async def draft_node(state: SupportState) -> dict:
    request = last_user_text(state)

    # Ground the writing in relevant best-practice guidance from the KB.
    tips = ""
    try:
        async with AsyncSessionLocal() as session:
            chunks = await hybrid_retriever.retrieve(session, request, top_k=3)
        if chunks:
            tips = "\n".join(f"- {c.content[:200]}" for c in chunks)
    except Exception as exc:  # noqa: BLE001
        logger.warning("draft_retrieval_skipped", error=str(exc))

    history = conversation_history(state, max_messages=6, include_current_turn=False)
    prompt = f"Recent conversation:\n{history}\n\nCurrent request: {request}" if history else request
    if tips:
        prompt = f"{prompt}\n\nApply these best-practice tips where relevant:\n{tips}"

    try:
        draft = await llm_service.chat(
            [SystemMessage(content=DRAFT_SYSTEM), HumanMessage(content=prompt)]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("draft_failed", error=str(exc))
        draft = "I couldn't draft that right now. Please try again shortly."

    guarded = check_output(draft)
    logger.info("draft_done", grounded=bool(tips))
    return {
        "answer": guarded.answer,
        "guard_output_flags": guarded.flags,
        "messages": [AIMessage(content=guarded.answer)],
    }
