"""Prometheus metrics (RED for HTTP, queue depth/age, pipeline and gateway outcomes).

``GET /api/metrics`` is **off unless ``METRICS_TOKEN`` is set** and then needs ``Authorization: Bearer <token>``; metric labels are route
*templates* and status classes only, never ids, emails or phone numbers.
"""

import time
from contextlib import contextmanager

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily

registry = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter("vitram_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=registry)
HTTP_DURATION = Histogram("vitram_http_request_duration_seconds", "HTTP request latency", ["method", "route"], registry=registry,
                          buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30))
HTTP_INFLIGHT = Gauge("vitram_http_requests_in_flight", "Requests being served", registry=registry)

JOBS_FINISHED = Counter("vitram_jobs_finished_total", "Job attempts by outcome", ["kind", "outcome"], registry=registry)  # done|retry|dead
JOB_DURATION = Histogram("vitram_job_duration_seconds", "Job handler duration", ["kind"], registry=registry,
                         buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300))
DOCUMENTS = Counter("vitram_documents_processed_total", "Documents through the pipeline", ["type", "outcome"], registry=registry)
GATEWAY = Counter("vitram_gateway_requests_total", "Calls to external gateways", ["gateway", "outcome"], registry=registry)
GATEWAY_DURATION = Histogram("vitram_gateway_request_duration_seconds", "External gateway call latency", ["gateway"], registry=registry,
                             buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30))
CIRCUIT = Gauge("vitram_circuit_state", "Circuit breaker state: 0 closed, 1 half-open, 2 open", ["dependency"], registry=registry)
SHED = Counter("vitram_load_shed_total", "Requests refused to protect the service", ["reason"], registry=registry)
RATE_LIMITED = Counter("vitram_rate_limited_total", "Requests refused by a rate limit", ["policy"], registry=registry)
CACHE = Counter("vitram_cache_total", "Cache lookups", ["cache", "result"], registry=registry)  # hit|miss


class _QueueCollector:
    """Reads queue depth at scrape time (cheap indexed counts), so the numbers are never stale."""

    def collect(self):
        from app.db import SessionLocal
        from app.services import jobs

        depth = GaugeMetricFamily("vitram_jobs", "Jobs by status", labels=["status"])
        age = GaugeMetricFamily("vitram_jobs_oldest_queued_age_seconds", "Age of the oldest runnable queued job")
        db = SessionLocal()
        try:
            s = jobs.stats(db)
        except Exception:  # noqa: BLE001 - a scrape must never fail because the database blinked
            db.rollback()
            return
        finally:
            db.close()
        for status in ("queued", "running", "dead", "done"):
            depth.add_metric([status], s[status])
        age.add_metric([], s["oldest_queued_age_seconds"] or 0)
        yield depth
        yield age


registry.register(_QueueCollector())


@contextmanager
def timed(histogram, *labels):
    start = time.perf_counter()
    try:
        yield
    finally:
        histogram.labels(*labels).observe(time.perf_counter() - start)


def route_template(scope: dict) -> str:
    path = getattr(scope.get("route"), "path", None)
    if not path:
        return "unmatched"
    return path if path.startswith("/api") else "/api" + path   # routers are mounted under /api


def render() -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST
