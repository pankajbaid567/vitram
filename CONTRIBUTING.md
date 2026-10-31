# Contributing

## Set up

```bash
make install        # backend (uv) + frontend (npm)
make api            # http://127.0.0.1:8000, SQLite, no keys needed
make web            # http://localhost:5173
```

Use **Open sample workspace** to explore. `make help` lists every task.

## Before you push

```bash
make ci             # ruff, oxlint, tsc, backend tests with coverage, frontend tests, build
make ci-linux       # the backend job in a Linux container (catches "works on my Mac")
make e2e            # browser smoke test (needs the API and a built web app running, plus Chrome)
```

CI runs the same checks on SQLite **and** PostgreSQL, plus a dependency audit, the browser e2e test and the accessibility audit.
Optional: `pip install pre-commit && pre-commit install`.

## Conventions

- **Layers.** Routers (`app/routers`) are the HTTP edge: authenticate, validate, call a service, shape the response. Business rules live in
  `app/services`; money maths lives in `app/services/finance` as pure functions with a `formula_version`. Don't put rules in routers.
- **Numbers are never invented.** Unknown terms return `computable: false` with what's missing. The assistant narrates tool results; it never calculates.
- **Every user-scoped query is scoped.** Add the route and `tests/test_access_matrix.py` will check isolation for you. A new public endpoint
  needs an entry (with a justification) in `app/public_routes.py`.
- **Schema changes need a migration** (`uv run alembic revision --autogenerate -m "…"`, then review it). Make it idempotent if a
  pre-Alembic database could already have the object. `tests/test_migrations.py` checks fresh, legacy and downgrade paths.
- **Providers sit behind ports** (`WhatsAppGateway`, the OCR providers). New vendor code belongs in an adapter, not in callers.
- **Tests are host-independent.** They must pass on macOS and Linux with no keys; real-device checks are opt-in markers.
- **Changing an API response?** `uv run python scripts/export_openapi.py` (CI fails if `docs/API.md` is stale) and, if the UI depends on it,
  `make fixtures`.
- **Comments say *why*.** The code says what.

## Reporting security problems

See [`SECURITY.md`](SECURITY.md).
