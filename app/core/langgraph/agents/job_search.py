"""Job-search agent — finds live jobs/salary data via Adzuna tools.

A bounded tool-calling loop (minimal ReAct): bind the live tools, let the model call
them, feed results back, and return the final answer. Degrades gracefully if no LLM
provider is configured or a tool errors.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.guardrails import check_output
from app.core.langgraph.agents.common import conversation_history, last_user_text
from app.core.langgraph.state import SupportState
from app.core.langgraph.tools import ACTION_TOOLS
from app.core.logging import get_logger
from app.core.prompts import JOB_SEARCH_SYSTEM
from app.services.llm import llm_service

logger = get_logger(__name__)

MAX_TOOL_STEPS = 4
_TOOL_MAP = {t.name: t for t in ACTION_TOOLS}


async def job_search_node(state: SupportState) -> dict:
    user_text = last_user_text(state)

    if not llm_service.has_providers:
        msg = (
            "I can't reach the job-search tools right now (no language model is "
            "configured). Please set an LLM API key and try again."
        )
        return {"answer": msg, "messages": [AIMessage(content=msg)]}

    history = conversation_history(state, max_messages=6, include_current_turn=False)
    seed = user_text
    if history:
        seed = (
            "Recent conversation (for follow-ups like \"find more like that\" or "
            f"\"same but in a different city\"):\n{history}\n\nCurrent request: {user_text}"
        )
    convo: list = [SystemMessage(content=JOB_SEARCH_SYSTEM), HumanMessage(content=seed)]
    tools_used: list[str] = []
    ai: AIMessage | None = None

    for step in range(MAX_TOOL_STEPS):
        try:
            ai = await llm_service.chat_with_tools(convo, ACTION_TOOLS)
        except Exception as exc:  # noqa: BLE001
            logger.warning("job_search_llm_error", step=step, error=str(exc))
            msg = "I ran into a problem searching jobs. Please try again shortly."
            return {"answer": msg, "messages": [AIMessage(content=msg)]}

        convo.append(ai)
        tool_calls = getattr(ai, "tool_calls", None) or []
        if not tool_calls:
            break

        for call in tool_calls:
            name = call.get("name")
            args = call.get("args", {}) or {}
            tool = _TOOL_MAP.get(name)
            if tool is None:
                result = f"Unknown tool: {name}"
            else:
                try:
                    result = await tool.ainvoke(args)
                    tools_used.append(name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("job_search_tool_error", tool=name, error=str(exc))
                    result = f"The '{name}' tool failed: {exc}"
            convo.append(ToolMessage(content=str(result), tool_call_id=call.get("id", name)))

    answer = ""
    if ai is not None:
        answer = ai.content if isinstance(ai.content, str) else str(ai.content)
    if not answer:
        answer = "I wasn't able to find that information right now."

    guarded = check_output(answer)
    logger.info("job_search_done", tools_used=tools_used)
    return {
        "answer": guarded.answer,
        "guard_output_flags": guarded.flags,
        "messages": [AIMessage(content=guarded.answer)],
    }
