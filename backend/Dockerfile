# syntax=docker/dockerfile:1
FROM python:3.15-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PIP_NO_CACHE_DIR=1
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra ai --extra postgres --extra s3 --extra otel --extra redis

FROM python:3.15-slim
ENV PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" ENV=production DATA_DIR=/data
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY fixtures ./fixtures
RUN useradd --system --uid 10001 vitram && mkdir /data && chown vitram /data
USER vitram
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
# --proxy-headers makes request.url.scheme reflect the proxy's HTTPS, so Secure cookies and HSTS work.
# Behind a trusted proxy only: widen FORWARDED_ALLOW_IPS to its address (default: loopback).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
