"""Request/response schemas for the chat API and internal agent contracts."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Route(str, Enum):
    """Where the supervisor can dispatch a turn."""

    KNOWLEDGE = "knowledge"      # career advice answerable from the KB (hybrid RAG)
    JOB_SEARCH = "job_search"    # find live jobs / salary data via Adzuna API
    DRAFT = "draft"             # draft a cover letter / resume bullets / outreach
    TRACK = "track"             # save a job/task to the user's application tracker
    ESCALATE = "escalate"        # hand off to a human career coach
    SMALLTALK = "smalltalk"      # greetings / chit-chat, no tools
    OUT_OF_SCOPE = "out_of_scope"  # politely refuse


class RouterDecision(BaseModel):
    """Structured output the supervisor LLM must return."""

    route: Route
    reason: str = Field(description="One-sentence justification for the route.")
    confidence: float = Field(ge=0.0, le=1.0)


class Citation(BaseModel):
    """A grounded source used to build the answer."""

    chunk_id: str
    document_title: str
    source: str
    snippet: str
    score: float


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(
        default=None,
        description="Client-supplied conversation id; a new one is minted if absent.",
    )


class GuardrailReport(BaseModel):
    input_flags: list[str] = Field(default_factory=list)
    output_flags: list[str] = Field(default_factory=list)
    blocked: bool = False


class ChatResponse(BaseModel):
    session_id: str
    route: Route
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    ticket_id: str | None = None
    needs_human: bool = False
    guardrails: GuardrailReport = Field(default_factory=GuardrailReport)


class TriageResult(BaseModel):
    """Structured output for saving an item to the application tracker."""

    category: Literal[
        "application", "interview", "follow_up", "offer", "task"
    ] = "application"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    subject: str
    summary: str
