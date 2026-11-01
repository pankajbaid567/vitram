# Observability

Three signals, all opt-in, all free to run. Nothing here sends data anywhere unless you configure it.

| Signal | Turn it on | Where it goes |
|---|---|---|
| **Logs** | always on; `LOG_FORMAT=json` for collectors | stdout. Every line carries `request_id`; phone numbers, keys and card numbers are redacted before formatting |
| **Metrics** | set `METRICS_TOKEN` | `GET /api/metrics` (Prometheus text, `Authorization: Bearer <token>`; 404 without a token) |
| **Traces** | install the `otel` extra and set `OTEL_EXPORTER_OTLP_ENDPOINT` | any OTLP/HTTP backend (Jaeger, Grafana Tempo, Honeycomb) |

The production image includes the `otel` extra, so enabling traces is configuration only.

## What is measured

- **HTTP (RED).** `vitram_http_requests_total{method,route,status}`, `vitram_http_request_duration_seconds` (histogram), `vitram_http_requests_in_flight`.
  `route` is the route *template* (`/api/goals/{goal_id}`), `status` is the class (`2xx`): no ids, emails or phone numbers become labels (a test
  asserts it).
- **Queue.** `vitram_jobs{status}` and `vitram_jobs_oldest_queued_age_seconds` are read from the database at scrape time, so they are never stale. The
  same numbers are in `GET /api/ready` under `checks.jobs` (`state: stale` after 10 minutes with a runnable job waiting; it does not make the API
  unready, because a stalled worker is an alert, not a reason to stop serving).
- **Work.** `vitram_jobs_finished_total{kind,outcome}` (`done`/`retry`/`dead`), `vitram_job_duration_seconds`, `vitram_documents_processed_total{type,outcome}`.
- **Dependencies and protection.** `vitram_gateway_requests_total{gateway,outcome}`, `vitram_gateway_request_duration_seconds`, `vitram_circuit_state{dependency}`,
  `vitram_load_shed_total`, `vitram_rate_limited_total`, `vitram_cache_total{cache,result}`.

## Traces

One server span per request, one client span per SQL statement (statement text only, **never bound parameters**), one per outbound HTTP call. The
request id is on the server span as `vitram.request_id`, so a log line and a trace join on the same id. Health, readiness and metrics are excluded.
SQL spans are produced by a small SQLAlchemy event hook (`app/tracing.py`) because the packaged instrumentor does not yet support the installed
SQLAlchemy 2.1.

Verified locally against Jaeger: one `GET /api/dashboard` is a single trace of 21 spans (the server span plus 17 SQL statements and ASGI sends),
carrying the request id. The span count is the picture of why the dashboard handler is the next candidate for caching (see `PERFORMANCE.md`).

## Run the whole stack locally

```bash
echo -n "$METRICS_TOKEN" > deploy/observability/metrics_token        # same value the API runs with
docker compose -f deploy/observability/docker-compose.yml up -d     # Prometheus :9090, Grafana :3000, Jaeger :16686
METRICS_TOKEN=... OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 uv run uvicorn app.main:app --port 18000
```

Grafana loads the **VITRAM API** dashboard (`deploy/observability/grafana/dashboards/vitram-api.json`): request rate, 5xx ratio, p50/p95/p99, slowest
routes, in-flight, shed/limited, queue depth and age, job outcomes and duration, documents by outcome, gateway calls and latency, circuit state and
cache hit ratio.

## Alerts

`deploy/observability/alerts.yml`:

| Alert | Fires when | Means |
|---|---|---|
| `ApiDown` | scrape fails 2 min | process or host down |
| `HighServerErrorRate` | > 2% 5xx for 5 min | something is broken; follow the `request_id` into the trace |
| `SlowReads` | read p95 > 1 s for 10 min (SLO is 300 ms) | a slow query or dependency |
| `JobQueueStalled` | oldest runnable job > 5 min for 5 min | no worker is draining documents |
| `DeadJobs` | any job parked dead in an hour | a document needs the user's Retry; look for the cause |
| `GatewayFailing` | > 20% of gateway calls fail for 10 min | WhatsApp/AI provider trouble |
| `CircuitOpen` | a circuit open 2 min | a feature is degraded on purpose |
| `LoadShedding` | any shedding for 5 min | the service is protecting itself |

On the free tier, point UptimeRobot (or the Cloudflare cron already in place) at `/api/ready` for `ApiDown`; the rest need a Prometheus you run.

## Reading an incident

1. A user quotes the reference from an error page: that is the `request_id`.
2. `grep` the JSON logs for it, or search Jaeger for `vitram.request_id = <id>`.
3. The trace shows which SQL statement or outbound call ate the time.
4. Check the dashboard for whether it is one route (query) or everything (host, database, dependency).
