"""Support-desk agent graph.

Workflow
--------

    ┌────────────┐
    │ supervisor │  input guardrail + LLM structured routing
    └─────┬──────┘
          │  (conditional on `route`)
   ┌──────┼─────────┬──────────┬───────────┬──────────────┐
   ▼      ▼         ▼          ▼           ▼              ▼
knowledge action  triage   escalate   smalltalk     out_of_scope
(hybrid  (live-API (create  (HITL +    (chit-chat)   (polite refuse)
 RAG)     tools)    ticket)  ticket)
   └──────┴─────────┴──────────┴───────────┴──────────────┘
                          ▼
                        END  → output guardrail already applied per-node

State is checkpointed per ``session_id`` (thread) so multi-turn conversations keep
their history. We use the Postgres checkpointer in real deployments and fall back
to an in-memory saver when Postgres is unavailable (e.g. unit tests).
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.core.langgraph.agents.draft import draft_node
from app.core.langgraph.agents.escalation import (
    escalation_node,
    out_of_scope_node,
    smalltalk_node,
)
from app.core.langgraph.agents.job_search import job_search_node
from app.core.langgraph.agents.knowledge import knowledge_node
from app.core.langgraph.agents.supervisor import supervisor_node
from app.core.langgraph.agents.triage import triage_node
from app.core.langgraph.state import SupportState
from app.core.logging import get_logger
from app.schemas.chat import Route

logger = get_logger(__name__)

_ROUTE_TO_NODE = {
    Route.KNOWLEDGE.value: "knowledge",
    Route.JOB_SEARCH.value: "job_search",
    Route.DRAFT.value: "draft",
    Route.TRACK.value: "track",
    Route.ESCALATE.value: "escalate",
    Route.SMALLTALK.value: "smalltalk",
    Route.OUT_OF_SCOPE.value: "out_of_scope",
}


def _route_selector(state: SupportState) -> str:
    if state.get("blocked"):
        return "out_of_scope"
    return _ROUTE_TO_NODE.get(state.get("route", ""), "track")


def build_graph(checkpointer=None):
    """Build and compile the support-desk state graph."""
    g = StateGraph(SupportState)

    g.add_node("supervisor", supervisor_node)
    g.add_node("knowledge", knowledge_node)
    g.add_node("job_search", job_search_node)
    g.add_node("draft", draft_node)
    g.add_node("track", triage_node)
    g.add_node("escalate", escalation_node)
    g.add_node("smalltalk", smalltalk_node)
    g.add_node("out_of_scope", out_of_scope_node)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges(
        "supervisor",
        _route_selector,
        {
            "knowledge": "knowledge",
            "job_search": "job_search",
            "draft": "draft",
            "track": "track",
            "escalate": "escalate",
            "smalltalk": "smalltalk",
            "out_of_scope": "out_of_scope",
        },
    )
    for node in (
        "knowledge", "job_search", "draft", "track", "escalate", "smalltalk",
        "out_of_scope",
    ):
        g.add_edge(node, END)

    return g.compile(checkpointer=checkpointer or MemorySaver())


class GraphManager:
    """Owns the compiled graph + its (async) Postgres checkpointer lifecycle."""

    def __init__(self) -> None:
        self._graph = None
        self._cm = None  # async context manager for the checkpointer

    async def startup(self) -> None:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            self._cm = AsyncPostgresSaver.from_conn_string(settings.checkpointer_dsn)
            saver = await self._cm.__aenter__()
            await saver.setup()
            self._graph = build_graph(checkpointer=saver)
            logger.info("graph_ready", checkpointer="postgres")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "postgres_checkpointer_unavailable_using_memory", error=str(exc)
            )
            self._graph = build_graph(checkpointer=MemorySaver())

    async def shutdown(self) -> None:
        if self._cm is not None:
            await self._cm.__aexit__(None, None, None)

    @property
    def graph(self):
        if self._graph is None:
            # Lazy fallback (e.g. tests that skip startup).
            self._graph = build_graph(checkpointer=MemorySaver())
        return self._graph


graph_manager = GraphManager()
