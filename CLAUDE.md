# CLAUDE.md

Guidance for Claude Code (and any AI pair-programmer) working in this repository.
Read this first before editing — it encodes the invariants that keep the project
correct.

## What this project is

A **production-style, multi-agent Career & Job Search Copilot** built on the
FastAPI + LangGraph template. A supervisor routes each turn to a specialist:
knowledge (career advice via **hybrid RAG**), job_search (live **Adzuna API** listings +
salary), draft (writes cover letters / resume bullets / outreach), track (saves items to
the job tracker), escalate, smalltalk, out_of_scope. Wrapped in **input/output
guardrails**, observable (structlog + Prometheus + optional Langfuse), and evaluated
offline (routing, guardrails, RAGAS) over 95 golden cases.


## Where things live

| Area | Path |
| --- | --- |
| Config (pydantic-settings) | `app/core/config.py` |
| FastAPI app + lifespan | `app/main.py` |
| API routes | `app/api/v1/endpoints/` |
| Agent graph (wiring) | `app/core/langgraph/graph.py` |
| Agent nodes | `app/core/langgraph/agents/` |
| Prompts | `app/core/prompts/__init__.py` |
| Guardrails | `app/core/guardrails/` |
| LLM service (fallback) | `app/services/llm.py` |
| Embeddings (local) | `app/services/embeddings.py` |
| Hybrid retrieval (RRF) | `app/services/retrieval.py` |
| Models (SQLModel) | `app/models/` |
| KB ingestion | `scripts/ingest_kb.py` |
| Evals | `evals/` |
| Tests | `tests/unit`, `tests/integration` |

## Golden rules (do not break these)

1. **Secrets only via settings.** Never read `os.environ` directly in app code;
   add a field to `Settings` in `app/core/config.py`. Secrets must be `SecretStr`.
   Never log a secret's value.
2. **Embedding dim must match everywhere.** `settings.embedding_dim`, the
   `Vector(...)` column in `app/models/kb.py`, and the chosen `EMBEDDING_MODEL`
   must agree. Changing the model means a migration + re-ingest.
3. **Nodes return partial state dicts**, never mutate the incoming state. Only
   `messages` uses append semantics (the `add_messages` reducer); everything else
   is last-write-wins.
4. **The router must always produce a valid `Route`.** On LLM failure it fails
   safe to `triage`. Keep that fallback.
5. **Guardrails never raise.** They return structured flags. Blocking is a
   decision made by the node/graph, not by the guardrail.
6. **Grounded answers only.** The knowledge node must answer strictly from
   retrieved context and cite `[n]`. Do not remove the groundedness check.
7. **Keep it free + light.** Embeddings are local (fastembed, CPU). LLMs are
   free-tier, OpenAI-compatible. Do not add paid or GPU-only dependencies.

## Common commands

```bash
make docker-up        # start db + api + prometheus + grafana
make ingest           # chunk + embed the knowledge base into Postgres
make seed             # create demo users
make test-unit        # fast offline tests
make eval             # routing + guardrail + RAGAS report
make lint             # ruff
make logs             # tail API logs
```

## How to extend

- **Add a tool:** create a `@tool` function in `app/core/langgraph/tools/`, then
  add it to `ACTION_TOOLS` (live-data tools the action agent can call) and/or
  `TOOLS` in that package's `__init__.py`. The action agent picks up `ACTION_TOOLS`
  automatically.
- **Add a specialist agent:** add a node in `app/core/langgraph/agents/`, register
  it in `build_graph()` (`app/core/langgraph/graph.py`), add a `Route` enum value
  in `app/schemas/chat.py`, extend `_ROUTE_TO_NODE`, and update the router prompt
  in `app/core/prompts/__init__.py`. Then add routing golden cases in
  `evals/golden/routing_golden.jsonl`.
- **Re-skin to another domain:** replace `data/knowledge_base/*.md`, adjust the
  triage categories + prompts in `app/core/prompts/__init__.py` and
  `app/schemas/chat.py`, swap the tools, and refresh the golden datasets.
- **Change retrieval:** edit `app/services/retrieval.py`. Keep both retrievers +
  RRF unless you have a measured reason (re-run `make eval` to prove no
  regression).

## Debugging tips

- 500s on `/chat`: check the API logs (`make logs`); the graph logs each routing
  decision and retrieval call with a `request_id`.
- Empty answers / "no info found": the KB probably isn't ingested — run
  `make ingest`.
- LLM errors: confirm at least one `LLMx_API_KEY` is set in `.env`. The service
  logs `no_llm_providers_configured` if none are.
- Postgres checkpointer warnings: the graph falls back to in-memory automatically;
  fix the DB connection to restore persistence.

## Definition of done for a change

- `make lint` and `make test-unit` pass.
- If you touched routing/retrieval/guardrails/prompts, `make eval` still passes
  its thresholds (see `evals/run_all.py`).
- New env vars are added to `Settings` (`app/core/config.py`) with a sane default
  or documented as required in the README/docs. There is no `.env.example` —
  `.env` is created by hand (see README.md Quickstart).
