"""Unit tests for conversation-history-awareness in the agent nodes."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.langgraph.agents.common import conversation_history, last_user_text
from app.core.langgraph.agents.draft import draft_node
from app.core.langgraph.agents.escalation import smalltalk_node
from app.core.langgraph.agents.job_search import job_search_node
from app.core.langgraph.agents.knowledge import knowledge_node
from app.services.retrieval import RetrievedChunk, hybrid_retriever


def _chunk(cid: str, content: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid,
        document_id="d",
        document_title="t",
        source="s",
        content=content,
        fused_score=1.0,
    )


# --------------------------------------------------------------------------
# Shared helpers (common.py)
# --------------------------------------------------------------------------


def test_last_user_text_returns_latest_human_message():
    state = {"messages": [HumanMessage(content="a"), AIMessage(content="b"), HumanMessage(content="c")]}
    assert last_user_text(state) == "c"


def test_last_user_text_empty_when_no_messages():
    assert last_user_text({}) == ""


def test_conversation_history_matches_legacy_8_message_window():
    messages = []
    for i in range(10):
        messages.append(HumanMessage(content=f"u{i}"))
        messages.append(AIMessage(content=f"a{i}"))
    state = {"messages": messages}

    legacy_parts = []
    for msg in messages:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        legacy_parts.append(f"{role}: {msg.content}")
    expected = "\n".join(legacy_parts[-8:])

    assert conversation_history(state) == expected


def test_conversation_history_exclude_current_turn():
    state = {"messages": [HumanMessage(content="a"), AIMessage(content="b"), HumanMessage(content="c")]}
    result = conversation_history(state, include_current_turn=False)
    assert result == "User: a\nAssistant: b"
    assert "c" not in result


def test_conversation_history_respects_max_messages():
    state = {
        "messages": [
            HumanMessage(content="a"),
            AIMessage(content="b"),
            HumanMessage(content="c"),
            AIMessage(content="d"),
        ]
    }
    assert conversation_history(state, max_messages=2) == "User: c\nAssistant: d"


def test_conversation_history_empty_state():
    assert conversation_history({}) == ""


# --------------------------------------------------------------------------
# knowledge_node
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_retrieval(monkeypatch):
    """Patch the shared retriever singleton (same object knowledge.py/draft.py hold)."""

    async def fake_retrieve(session, query, top_k=None):
        fake_retrieve.last_query = query
        return [_chunk("1", "Prepare examples using the STAR method for behavioral interviews.")]

    monkeypatch.setattr(hybrid_retriever, "retrieve", fake_retrieve)
    return fake_retrieve


async def test_knowledge_node_includes_prior_turn_in_prompt(fake_llm):
    state = {
        "messages": [
            HumanMessage(content="I'm interested in finance industry careers"),
            AIMessage(content="Great, here's some general advice [1]."),
            HumanMessage(content="What interview questions should I prepare for in that field?"),
        ]
    }
    await knowledge_node(state)
    sent_prompt = fake_llm.chat_calls[-1][-1].content
    assert "finance" in sent_prompt


async def test_knowledge_node_retrieval_query_is_last_turn_only(fake_llm, _patch_retrieval):
    state = {
        "messages": [
            HumanMessage(content="I'm interested in finance industry careers"),
            AIMessage(content="Great, here's some general advice [1]."),
            HumanMessage(content="What interview questions should I prepare for in that field?"),
        ]
    }
    await knowledge_node(state)
    assert _patch_retrieval.last_query == "What interview questions should I prepare for in that field?"
    assert "finance" not in _patch_retrieval.last_query


async def test_knowledge_node_groundedness_flag_still_fires(fake_llm):
    fake_llm.chat_response = "Completely unrelated gibberish about volcanoes and spaceships."
    state = {"messages": [HumanMessage(content="How do I prepare for interviews?")]}
    result = await knowledge_node(state)
    assert "low_groundedness" in result["guard_output_flags"]


async def test_knowledge_node_groundedness_passes_when_grounded(fake_llm):
    fake_llm.chat_response = (
        "Prepare examples using the STAR method for behavioral interviews [1]."
    )
    state = {"messages": [HumanMessage(content="How do I prepare for interviews?")]}
    result = await knowledge_node(state)
    assert "low_groundedness" not in result["guard_output_flags"]


async def test_knowledge_node_single_turn_prompt_unchanged(fake_llm):
    state = {"messages": [HumanMessage(content="How do I prepare for interviews?")]}
    await knowledge_node(state)
    sent_prompt = fake_llm.chat_calls[-1][-1].content
    assert "Recent conversation" not in sent_prompt


# --------------------------------------------------------------------------
# job_search_node
# --------------------------------------------------------------------------


async def test_job_search_node_seeds_convo_with_history(fake_llm):
    state = {
        "messages": [
            HumanMessage(content="find data analyst jobs in Berlin"),
            AIMessage(content="I found a few data analyst roles in Berlin for you."),
            HumanMessage(content="find more like that"),
        ]
    }
    await job_search_node(state)
    seeded = fake_llm.chat_with_tools_calls[0][-1].content
    assert "Berlin" in seeded
    assert "data analyst" in seeded


async def test_job_search_node_single_turn_unaffected(fake_llm):
    state = {"messages": [HumanMessage(content="find data analyst jobs in Berlin")]}
    await job_search_node(state)
    seeded = fake_llm.chat_with_tools_calls[0][-1].content
    assert seeded == "find data analyst jobs in Berlin"


async def test_job_search_node_no_providers_configured(fake_llm):
    fake_llm.has_providers = False
    state = {"messages": [HumanMessage(content="find data analyst jobs in Berlin")]}
    result = await job_search_node(state)
    assert "configured" in result["answer"] or "API key" in result["answer"]
    assert fake_llm.chat_with_tools_calls == []


# --------------------------------------------------------------------------
# draft_node
# --------------------------------------------------------------------------


async def test_draft_node_includes_prior_turn_for_followup(fake_llm, monkeypatch):
    async def no_chunks(session, query, top_k=None):
        return []

    monkeypatch.setattr(hybrid_retriever, "retrieve", no_chunks)
    state = {
        "messages": [
            HumanMessage(content="Write a cover letter for a Data Analyst role at Acme Corp"),
            AIMessage(content="Dear Hiring Manager, ..."),
            HumanMessage(content="Make it shorter"),
        ]
    }
    await draft_node(state)
    sent_prompt = fake_llm.chat_calls[-1][-1].content
    assert "Acme Corp" in sent_prompt


async def test_draft_node_single_turn_unaffected(fake_llm, monkeypatch):
    async def no_chunks(session, query, top_k=None):
        return []

    monkeypatch.setattr(hybrid_retriever, "retrieve", no_chunks)
    state = {"messages": [HumanMessage(content="Write a cover letter for Acme Corp")]}
    await draft_node(state)
    sent_prompt = fake_llm.chat_calls[-1][-1].content
    assert sent_prompt == "Write a cover letter for Acme Corp"


# --------------------------------------------------------------------------
# smalltalk_node
# --------------------------------------------------------------------------


async def test_smalltalk_node_includes_prior_turn(fake_llm):
    state = {
        "messages": [
            HumanMessage(content="I love hiking on weekends"),
            AIMessage(content="That's great! How can I help with your career search?"),
            HumanMessage(content="thanks!"),
        ]
    }
    await smalltalk_node(state)
    sent_prompt = fake_llm.chat_calls[-1][-1].content
    assert "hiking" in sent_prompt


async def test_smalltalk_node_single_turn_unaffected(fake_llm):
    state = {"messages": [HumanMessage(content="hi there")]}
    await smalltalk_node(state)
    sent_prompt = fake_llm.chat_calls[-1][-1].content
    assert sent_prompt == "hi there"
