# Architecture & Workflow

This document traces a request end-to-end so the project's working is unambiguous.

## 1. Request lifecycle

1. **HTTP in.** `POST /api/v1/chat` with a bearer JWT and `{ "message": ... }`.
2. **Middleware.** `ContextLoggingMiddleware` binds a `request_id` to the logging
   context and starts a latency timer. Every downstream log line carries the id.
3. **Auth.** `get_current_user` validates the JWT and loads the user.
4. **Rate limit.** slowapi enforces `20/minute` per user on the chat route.
5. **Graph invocation.** The endpoint builds the initial state and calls
   `graph_manager.graph.ainvoke(state, config={"configurable": {"thread_id": session_id}})`.
   The `thread_id` is the `session_id`, so LangGraph loads prior turns from the
   Postgres checkpointer (multi-turn memory).
6. **Response out.** The final state is mapped to `ChatResponse` (answer,
   citations, route, ticket id, guardrail report) and returned.

## 2. The graph

Defined in `app/core/langgraph/graph.py`.

```
START ──▶ supervisor ──(conditional on route)──▶ {knowledge|action|triage|escalate|smalltalk|out_of_scope} ──▶ END
```

### supervisor (`agents/supervisor.py`)

- Runs the **input guardrail** first (`check_input`). If the input is blocked
  (e.g. too long) it short-circuits to `out_of_scope`. A `self_harm_signal` forces
  `escalate` with `needs_human=True` regardless of the model.
- Otherwise asks the LLM for a **structured** `RouterDecision` (route + reason +
  confidence). Structured output means we get a validated enum, not free text.
- On any LLM failure it **fails safe to `triage`** (a human-reviewable ticket)
  rather than dropping the request.
- Emits the `agent_route_total` metric.

### knowledge (`agents/knowledge.py`)

- Calls the **hybrid retriever** (see §3) for the top-k chunks.
- If nothing is found, offers to open a ticket (no hallucinated answer).
- Otherwise builds a numbered context block and asks the LLM to answer **using
  only that context**, citing `[n]`.
- Runs the **output guardrail** with `require_grounding=True`. If groundedness is
  below threshold it appends an uncertainty caveat and flags `low_groundedness`.
- Returns `answer`, `citations`, and appends an `AIMessage` to state.

### action (`agents/action.py`)

- Handles requests that need **live data**. Binds the external-API tools
  (`get_weather`, `get_country_info`, `convert_currency`) to the LLM and runs a
  bounded tool-calling loop (max 4 steps): the model requests a tool, the node
  executes it, feeds the result back, and repeats until the model produces a final
  answer.
- Every tool hits a **free, keyless public API** (Open-Meteo, REST Countries,
  Frankfurter), so it works with no extra setup.
- Degrades gracefully: if no LLM provider is configured, or a tool errors, the user
  gets a clear message instead of a failure.

### triage (`agents/triage.py`)

- Extracts a **structured** `TriageResult` (category, priority, subject, summary).
- Persists a `Ticket` row and returns a confirmation with the ticket id.

### escalate (`agents/escalation.py`)

- Produces an empathetic hand-off message and opens a **high-priority**,
  `pending_human` ticket assigned to the escalation queue.
- Sets `needs_human=True`. (The node is also where a LangGraph `interrupt` would
  pause the graph for a true human-in-the-loop resume; the default HTTP path
  returns immediately and leaves the ticket for a human.)

### smalltalk / out_of_scope

- `smalltalk` replies briefly and steers back to support.
- `out_of_scope` returns a fixed polite refusal (also the sink for blocked input
  and adversarial prompts).

## 3. Hybrid retrieval (`services/retrieval.py`)

Two retrievers run against the same Postgres table, then fuse:

- **Semantic.** The query is embedded locally (fastembed, `bge-small`) and matched
  against the `embedding vector(384)` column with pgvector cosine distance
  (`<=>`), backed by an IVFFlat index.
- **Keyword.** Postgres `websearch_to_tsquery` + `ts_rank_cd` over the generated
  `content_tsv` column, backed by a GIN index. This nails exact tokens (error
  codes like `E-1004`, SKUs) that dense search can miss.
- **Fusion (RRF).** Reciprocal Rank Fusion combines the two ranked lists:
  `score(d) = Σ 1/(k + rank_i(d))` with `k=60`. It needs no score calibration and
  is the de-facto production default. Documents appearing in **both** lists rise
  to the top.

Why both? Semantic handles paraphrase ("card was declined" ≈ "payment failed");
keyword handles exact/rare terms. Hybrid + RRF beats either alone on recall.

## 4. State (`core/langgraph/state.py`)

`SupportState` is a `TypedDict`. `messages` uses the `add_messages` reducer
(append); all other keys are last-write-wins. Nodes return **partial** dicts of
just the keys they change — they never mutate the incoming state.

## 5. Persistence

- **Conversation memory:** LangGraph Postgres checkpointer, keyed by `session_id`.
- **Domain data:** SQLModel tables — `users`, `kb_documents`, `kb_chunks`,
  `tickets`. Managed by Alembic (`migrations/`), bootstrapped by `init_db()` in
  dev.

## 6. Resilience: the LLM service (`services/llm.py`)

- Each provider is a `ChatOpenAI` client pointed at an OpenAI-compatible endpoint.
- **Per-call:** `tenacity` exponential-backoff retry for transient errors.
- **Across providers:** if the primary exhausts retries, rotate to the next
  configured provider (circular fallback). A total-timeout budget bounds latency.
- **Structured output:** `structured(messages, schema)` binds a Pydantic model so
  routing/triage return validated objects.
- Configured providers are discovered from `.env`; missing keys are skipped.

## 7. Observability

- **Logs:** structlog, JSON in non-local envs, with `request_id`/`session_id`.
- **Metrics:** Prometheus at `/metrics` — HTTP rate/latency, route distribution,
  LLM latency + fallback count, retrieval latency/hits, guardrail blocks.
- **Dashboards:** Grafana auto-provisioned (`grafana/`).
- **Tracing:** optional Langfuse (`LANGFUSE_TRACING_ENABLED=true`).

## 8. Extending the desk

See the "How to extend" section in [`../CLAUDE.md`](../CLAUDE.md).
