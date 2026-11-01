"""OpenTelemetry tracing, opt-in.

Set ``OTEL_EXPORTER_OTLP_ENDPOINT`` (and install the ``otel`` extra) to export traces; otherwise this module does nothing and the app
has no OpenTelemetry cost. Spans cover each HTTP request, every SQL statement and every outbound ``httpx`` call, and the request id
is attached to the server span (``vitram.request_id``, set by the security middleware) so a log line and a trace can be joined.
"""

import logging
import os

log = logging.getLogger("vitram.tracing")


def _trace_sql(engine, provider) -> None:
    """One client span per SQL statement. Written against SQLAlchemy's events because the packaged instrumentor lags the installed
    SQLAlchemy version. The span carries the statement text only, never bound parameters, so no user data reaches the trace backend."""
    from opentelemetry.trace import SpanKind
    from sqlalchemy import event

    tracer = provider.get_tracer("vitram.sql")
    system = engine.dialect.name

    @event.listens_for(engine, "before_cursor_execute")
    def _start(conn, cursor, statement, parameters, context, executemany):
        verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "SQL"
        span = tracer.start_span(f"SQL {verb}", kind=SpanKind.CLIENT,
                                 attributes={"db.system": system, "db.statement": statement[:500]})
        conn.info.setdefault("_otel_spans", []).append(span)

    def _end(conn):
        spans = conn.info.get("_otel_spans")
        if spans:
            spans.pop().end()

    @event.listens_for(engine, "after_cursor_execute")
    def _done(conn, cursor, statement, parameters, context, executemany):
        _end(conn)

    @event.listens_for(engine, "handle_error")
    def _failed(ctx):
        _end(ctx.connection) if ctx.connection is not None else None


def setup(app, exporter=None) -> bool:
    """Instrument ``app`` if tracing is configured. ``exporter`` lets tests inject an in-memory exporter. Returns True when active."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint and exporter is None:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    except ImportError:
        log.warning("OTEL_EXPORTER_OTLP_ENDPOINT is set but the 'otel' extra is not installed; tracing stays off")
        return False

    from app.db import engine

    provider = TracerProvider(resource=Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "vitram-api")}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls="/api/health,/api/ready,/api/metrics")
    _trace_sql(engine, provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    log.info("tracing enabled")
    return True
