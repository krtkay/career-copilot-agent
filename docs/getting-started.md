# Getting Started

## Option A — Docker (recommended)

Prerequisites: Docker + Docker Compose, one LLM API key.

```bash
cat > .env <<'EOF'
LLM1_NAME=openai
LLM1_MODEL=gpt-4o-mini
LLM1_BASE_URL=https://api.openai.com/v1
LLM1_API_KEY=<your key>
EOF
make docker-up                # db + api + prometheus + grafana
make ingest                   # chunk + embed the KB
make seed                     # demo users
```

- API docs: <http://localhost:8000/docs>
- Grafana: <http://localhost:3000> (admin/admin)
- Prometheus: <http://localhost:9090>

## Option B — Local (no Docker for the app)

You still need Postgres with pgvector. Fastest is to run just the DB in Docker:

```bash
docker run -d --name support-db -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=support_desk \
  pgvector/pgvector:pg16

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,evals]"

printf 'POSTGRES_HOST=localhost\nLLM1_NAME=openai\nLLM1_MODEL=gpt-4o-mini\nLLM1_BASE_URL=https://api.openai.com/v1\nLLM1_API_KEY=<your key>\n' > .env
alembic upgrade head          # or rely on init_db() at startup
python -m scripts.ingest_kb --reset
python -m scripts.seed_users
uvicorn app.main:app --reload
```

## Getting an LLM key

You only need **one**; the rest act as automatic fallbacks.

- **OpenAI** (primary — paid, cheap + reliable, `gpt-4o-mini`, supports structured
  outputs for routing): <https://platform.openai.com/api-keys> → `LLM1_API_KEY`.
- **Groq** (fallback — fast, free tier, `openai/gpt-oss-120b`): <https://console.groq.com/keys> →
  `LLM2_API_KEY`.
- **Gemini** (OpenAI-compatible endpoint): <https://aistudio.google.com/apikey> →
  `LLM3_API_KEY`.

Prefer fully offline? Point a provider at a local **Ollama** server
(`http://localhost:11434/v1`) — localhost endpoints need no key.

## First-run notes

- The **embedding model (~130 MB)** downloads on first use (or is baked into the
  Docker image). It's local and CPU-only — no GPU, no embedding bills.
- `init_db()` enables the `vector` and `pg_trgm` extensions and creates tables on
  startup for convenience; production changes go through Alembic.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `/chat` returns "couldn't find anything" | KB not ingested → `make ingest`. |
| `no_llm_providers_configured` in logs | No `LLMx_API_KEY` set in `.env`. |
| 500 on `/chat` | `make logs`; each turn logs its route + retrieval with a `request_id`. |
| `postgres_checkpointer_unavailable` warning | DB unreachable; graph falls back to in-memory memory. Fix the connection to persist conversations. |
| pgvector errors on ingest | Ensure the DB image is `pgvector/pgvector` and the `vector` extension is enabled (it is, via `init_db`/migration). |
| Slow first request | Embedding model loading; subsequent requests are fast. |

## Useful commands

```bash
make help          # list everything
make test-unit     # fast offline tests
make eval          # quality report
make lint          # ruff
make logs          # tail API logs
make docker-down   # stop the stack
```
