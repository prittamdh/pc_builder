# One image for the API and the pipeline worker (plan 03-02). Built on the server itself,
# so it is arm64 there (Ampere A1) and amd64 on a developer PC; every dependency ships
# wheels for both.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY src ./src
COPY scripts ./scripts
COPY data ./data

# Never run as root. The worker rewrites data/brand_registry.json each cycle.
RUN useradd --system --uid 10001 --home /app app && chown -R app:app /app
USER app

EXPOSE 8000
# One process: the rate limiter keeps its counters in memory (see .env.example), so
# extra workers would multiply every limit. Only Caddy on the private Docker network
# reaches this port, so trusting its X-Forwarded-* headers is safe.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
