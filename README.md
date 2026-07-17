# AI Career & Job Search Copilot

A **production-style, multi-agent career assistant** built on FastAPI + LangGraph. It
solves one clear, real problem: **help someone run their job search** — answer career
questions with grounded advice, find real live job listings, look up real salary data,
and draft the documents they need (cover letters, outreach, resume bullets).

It runs for **free** on a laptop (local embeddings + free-tier LLM APIs + a free Adzuna
key) and includes the layers a real deployment needs: routing, retrieval, real tool use,
guardrails, evaluation, observability, auth, rate limiting, migrations, and Docker.

Built on the [`fastapi-langgraph-agent-production-ready-template`](https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template)
conventions.

---

## What it does

A supervisor agent classifies each message and routes it to a specialist:

| Route | Agent | What it does |
| --- | --- | --- |
| `knowledge` | Career coach | Answers resume/ATS, interview (STAR), salary, cover-letter, and job-search questions from the KB using **hybrid retrieval**, grounded and cited. |
| `job_search` | Job finder | Calls the **real Adzuna Jobs API** to return live listings and salary insights via LLM tool-calling. |
| `draft` | Career writer | Writes a tailored **cover letter, resume bullets, or outreach message** — a real deliverable, grounded in the KB's best practices. |
| `track` | Tracker | Saves an application / interview / follow-up to the user's job tracker. |
| `escalate` | Coach hand-off | Routes to a human career coach. |
| `smalltalk` / `out_of_scope` | — | Friendly chit-chat / polite refusal. |

Every turn passes through **input guardrails** (PII, prompt-injection, length) and
**output guardrails** (PII redaction, groundedness on KB answers).

### The knowledge base (real content)

Fourteen evergreen articles in `data/knowledge_base/`, written from authoritative sources
(Indeed, Columbia & MIT career centers, BigInterview, Remote, and established career
guidance): **ATS & resume formatting**, **resume writing**, **STAR / behavioral interviews**, **phone / video / panel interviews**, **common interview questions**, **informational interviews & networking**, **salary negotiation**, **references, offers & counteroffers**, **cover letters & outreach**, **job-search strategy & foundations**, **LinkedIn**, **remote job searching**, and **career change & growth**.

### The live tool (real external API — free)

- **Adzuna Jobs API** — real job listings + salary histogram data across many countries.
  Free key at <https://developer.adzuna.com>. The `search_jobs` and `get_salary_insights`
  tools are the load-bearing external calls.

## Architecture

```
Client ──HTTP──▶ FastAPI (auth · rate-limit · request-id · metrics)
                     │
                     ▼
               LangGraph graph  ── checkpointed per session_id (Postgres)
                     │  input guardrail
                supervisor  (LLM structured routing)
                     │  conditional edge on `route`
   ┌─────────┬───────┼────────┬────────┬──────────┬─────────────┐
   ▼         ▼       ▼        ▼        ▼          ▼             ▼
knowledge job_search draft   track  escalate  smalltalk   out_of_scope
 hybrid    Adzuna   write    save    human
  RAG      tools    docs     item    coach
                     │  output guardrail (PII redaction + groundedness)
                     ▼
                  Response  (answer + citations + route + tracker item + guardrails)
```

## Tech stack

- **API:** FastAPI, JWT auth, slowapi rate limiting, Prometheus `/metrics`
- **Agents:** LangGraph supervisor + specialists (incl. a tool-calling job-search agent
  and a document-drafting agent), Postgres checkpointing
- **LLM:** any OpenAI-compatible provider (OpenAI / Groq / Gemini) with retry +
  circular fallback
- **Tool:** Adzuna Jobs API (free, keyed)
- **Retrieval:** Postgres + **pgvector** (semantic) + **full-text** (keyword), fused with
  Reciprocal Rank Fusion
- **Embeddings:** `fastembed` (`bge-small-en-v1.5`, 384-dim) — local, CPU, free
- **Guardrails:** deterministic PII / injection / groundedness checks
- **Evals:** RAGAS + routing accuracy + guardrail precision — **95 golden test cases**
- **Observability:** structlog, Prometheus, Grafana dashboard, optional Langfuse
- **Ops:** Docker Compose, Alembic, ruff, pre-commit, pytest

---

## Quickstart (Docker)

**Prerequisites:** Docker + Compose, one LLM key (OpenAI: <https://platform.openai.com/api-keys>,
paid but cheap — `gpt-4o-mini`; or Groq's free tier: <https://console.groq.com/keys>,
see [docs/getting-started.md](docs/getting-started.md)), and optionally a free Adzuna
key (<https://developer.adzuna.com>) for live job search.

```bash
cat > .env <<'EOF'
LLM1_NAME=openai
LLM1_MODEL=gpt-4o-mini
LLM1_BASE_URL=https://api.openai.com/v1
LLM1_API_KEY=<your key from https://platform.openai.com/api-keys>
EOF
#   → optionally also add ADZUNA_APP_ID / ADZUNA_APP_KEY, or more LLM providers
#     as LLM2_*/LLM3_*/LLM4_* — see app/core/config.py for every setting.
make docker-up      # db + api + prometheus + grafana
make ingest         # chunk + embed the knowledge base
make seed           # demo users
```

Try it at <http://localhost:8000/docs>, or via curl:

```bash
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"user-password-123"}' | jq -r .access_token)

# knowledge (grounded + cited)
curl -s http://localhost:8000/api/v1/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"message":"How do I optimize my resume for an ATS?"}' | jq

# job_search (live Adzuna API)
curl -s http://localhost:8000/api/v1/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"message":"Find data analyst jobs in London"}' | jq

# draft (real deliverable)
curl -s http://localhost:8000/api/v1/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"message":"Write a cover letter for a data scientist role at Acme"}' | jq
```

Dashboards: **Grafana** <http://localhost:3000> (admin/admin) · **Prometheus** <http://localhost:9090>.

## Streamlit frontend

```bash
pip install -r frontend/requirements.txt
streamlit run frontend/streamlit_app.py     # or: make frontend
```
Open <http://localhost:8501>, sign in with the demo user (`user@example.com` /
`user-password-123`).

## Evaluations

```bash
make eval        # routing accuracy + guardrail precision + RAGAS over 95 golden cases
```

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — full workflow and data flow
- [`docs/evaluation.md`](docs/evaluation.md) — golden datasets, RAGAS, CI gate
- [`docs/guardrails.md`](docs/guardrails.md) — guardrail design
- [`docs/getting-started.md`](docs/getting-started.md) — setup + troubleshooting
- [`docs/langfuse.md`](docs/langfuse.md) — enable LLM tracing with Langfuse
- [`CLAUDE.md`](CLAUDE.md) — guidance for editing/debugging with Claude Code
- [`RUNBOOK.md`](RUNBOOK.md) — step-by-step run & validation (adapt the domain examples)

## License

MIT.
