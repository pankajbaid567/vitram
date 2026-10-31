# Common tasks. `make help` lists them.
.DEFAULT_GOAL := help
.PHONY: help install api web test test-backend test-frontend lint e2e a11y ci ci-linux fixtures up down audit

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Install backend and frontend dependencies
	cd backend && uv sync --extra ai
	cd frontend && npm install

api:  ## Run the API on :8000 (SQLite, no keys needed)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

web:  ## Run the web app on :5173 (proxies /api; override with API_PROXY_TARGET=...)
	cd frontend && npm run dev

test-backend:  ## Backend tests with coverage
	cd backend && uv run pytest -q --cov=app

test-frontend:  ## Frontend tests
	cd frontend && npm test

test: test-backend test-frontend  ## All unit and API tests

lint:  ## Ruff, oxlint and the TypeScript compiler
	cd backend && uv run ruff check .
	cd frontend && npm run lint && npm run typecheck

e2e:  ## Browser smoke test (needs `make api` and a built `npm run preview` on :5173, plus Chrome)
	cd frontend && node scripts/e2e.mjs

a11y:  ## Accessibility audit (same prerequisites as e2e)
	cd frontend && node scripts/a11y-audit.mjs

audit:  ## Known-vulnerability scan of both dependency trees
	cd backend && uv export --frozen --no-hashes --no-dev --extra ai --extra postgres --no-emit-project > /tmp/vitram-requirements.txt && uvx pip-audit -r /tmp/vitram-requirements.txt --no-deps --disable-pip
	cd frontend && npm audit --audit-level=high

ci: lint test  ## What CI checks, minus the browser jobs
	cd frontend && npm run build

ci-linux:  ## Reproduce the backend CI job in a Linux container (catches "works on my Mac")
	docker run --rm -v "$$PWD/backend:/src:ro" python:3.12-slim sh -c "cp -r /src /w && cd /w && rm -rf .venv .data && pip install -q uv && uv sync --frozen --extra ai --extra postgres && uv run ruff check . && uv run pytest -q --cov=app --cov-fail-under=80"

fixtures:  ## Re-capture frontend test fixtures from a running API (default http://localhost:8000)
	cd backend && uv run python scripts/capture_frontend_fixtures.py $(or $(API),http://localhost:8000)

up:  ## Full stack in containers (PostgreSQL + API + worker + web) on :8080
	docker compose up --build

down:  ## Stop the containers
	docker compose down
