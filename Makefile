.DEFAULT_GOAL := help
.PHONY: help install env docker-up docker-down logs ingest seed run frontend test test-unit \
        lint format eval migrate revision

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install app + dev + eval dependencies
	pip install -e ".[dev,evals]"

env: ## Fail with a clear message if .env is missing
	@test -f .env || (echo "No .env found. Create one with at least LLM1_NAME, LLM1_MODEL, LLM1_BASE_URL, and LLM1_API_KEY (see README.md Quickstart / app/core/config.py for the full list of settings)." && exit 1)

docker-up: env ## Build and start the full stack (db, api, prometheus, grafana)
	docker compose up --build -d
	@echo "API:        http://localhost:8000/docs"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana:    http://localhost:3000 (admin/admin)"

docker-down: ## Stop the stack
	docker compose down

logs: ## Tail API logs
	docker compose logs -f api

ingest: ## Ingest the knowledge base (chunks + embeddings)
	docker compose exec api python -m scripts.ingest_kb --reset

seed: ## Create demo users (user@ / agent@)
	docker compose exec api python -m scripts.seed_users

run: ## Run the API locally (needs a local Postgres + .env)
	uvicorn app.main:app --reload --port 8000

frontend: ## Run the Streamlit frontend (backend must be up)
	pip install -r frontend/requirements.txt
	streamlit run frontend/streamlit_app.py

test: ## Run all tests
	pytest

test-unit: ## Run only unit tests (fast, offline)
	pytest -m "not integration" tests/unit

lint: ## Lint with ruff
	ruff check app tests evals scripts

format: ## Auto-format with ruff
	ruff check --fix app tests evals scripts
	ruff format app tests evals scripts

eval: ## Run the full evaluation suite (routing + guardrails + RAGAS)
	docker compose exec api python -m evals.run_all

migrate: ## Apply Alembic migrations
	docker compose exec api alembic upgrade head

revision: ## Autogenerate a new Alembic migration (msg="...")
	docker compose exec api alembic revision --autogenerate -m "$(msg)"
