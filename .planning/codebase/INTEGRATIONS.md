---
last_mapped_commit: a803b6fdb669c9fb39477658b3e08c0a134f8cf2
last_mapped_at: 2026-09-24
---
# External Integrations

**Analysis Date:** 2026-09-24

## APIs & External Services

**LLM Providers (OpenAI-compatible chat completions):**
- Mistral - Title/spec extraction via `ministral-14b-latest` model
  - SDK/Client: httpx
  - Endpoint: `https://api.mistral.ai/v1/chat/completions`
  - Auth: `MISTRAL_API_KEY` environment variable
  - Primary choice in extraction pipeline (highest throughput, 8/8 accuracy on test set)

- Google Gemini - Fallback title/spec extraction via `gemini-3.1-flash-lite` model
  - SDK/Client: httpx (OpenAI-compatible endpoint)
  - Endpoint: `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`
  - Auth: `GOOGLE_API_KEY` environment variable
  - Second in provider chain; reliable fallback

- Groq - Fallback title/spec extraction via `openai/gpt-oss-120b` model
  - SDK/Client: httpx (OpenAI-compatible endpoint)
  - Endpoint: `https://api.groq.com/openai/v1/chat/completions`
  - Auth: `GROQ_API_KEY` environment variable
  - Note: Original `llama-3.1-8b-instant` model deprecated; now uses OSS model
  - Free tier limited to 1-2 calls per minute; unsuitable for bulk extraction

- Cerebras - Fallback title/spec extraction via `gpt-oss-120b` model
  - SDK/Client: httpx (OpenAI-compatible endpoint)
  - Endpoint: `https://api.cerebras.ai/v1/chat/completions`
  - Auth: `CEREBRAS_API_KEY` environment variable
  - Returns 402 Payment Required on free tier; not actively used

- NVIDIA NIM - Mentioned for potential fallback (`nvidia/mistral-nemotron`); implementation available as drop-in swap
  - Auth: `NVIDIA_API_KEY` environment variable
  - Endpoint integration: via same OpenAI-compatible pattern in provider chain

**Extraction Service:**
- Location: `src/services/groq_extraction_service.py`
- Strategy: Tries providers in order; rolls to next on failure (429, 402, timeout, quota exhausted)
- All providers implement OpenAI-compatible `/v1/chat/completions` API
- Used for: CPU, GPU, RAM, PSU, motherboard, cooler, cabinet, monitor title and specification extraction from product listings

## Data Storage

**Databases:**
- PostgreSQL 15 (Alpine Linux Docker image)
  - Connection: `DATABASE_URL` environment variable
  - Client: SQLAlchemy 2.0.0+ ORM, psycopg[binary] adapter
  - Pool pre-ping enabled for connection stability
  - Docker service: `postgres` container on `postgres:5432` (internal to Docker network)
  - External port: `5432` mapped to host
  - Admin tool: pgAdmin 4 on port `5050` for database browsing and management

**File Storage:**
- Local filesystem only - no cloud storage integration
- Data directories: `data/raw/`, `data/processed/`, `data/exports/`, `data/cache/`
- Log files: `logs/pc_builder.log`
- Static UI: `src/static/`

**Caching:**
- None - requests are not cached; rely on web scraping retries and database memoization

## Authentication & Identity

**Auth Provider:**
- Custom / None - No centralized authentication system
- API endpoints are unauthenticated (CORS enabled for all origins)
- Airflow web UI requires login via `AIRFLOW_WEBSERVER_SECRET_KEY` and Fernet encryption
- LLM provider authentication via API keys (environment variables)

## Monitoring & Observability

**Error Tracking:**
- None detected - no Sentry, Rollbar, or similar service

**Logs:**
- File-based: `logs/pc_builder.log`
- Log level: Configurable via `LOG_LEVEL` environment variable
- Logger: Standard Python logging module via `src/common/logger.py`
- Airflow logs: `logs/` directory (mounted in Docker)

## CI/CD & Deployment

**Hosting:**
- Local development: Python 3.12+ interpreter + PostgreSQL Docker container
- Docker Compose: Full stack (PostgreSQL, pgAdmin, Apache Airflow)
- No cloud deployment detected (not AWS, GCP, Azure, Vercel, etc.)

**CI Pipeline:**
- None detected - no GitHub Actions, GitLab CI, or similar configured

## Environment Configuration

**Required Environment Variables:**
- `DATABASE_URL` - PostgreSQL connection string (critical; default provided but overridable)
- `GROQ_API_KEY` - For LLM extraction (optional if other LLM APIs provided)
- `MISTRAL_API_KEY` - For LLM extraction (recommended; highest throughput)
- `GOOGLE_API_KEY` - For LLM extraction (recommended fallback)
- `POSTGRES_PASSWORD` - PostgreSQL credentials (required for Docker)
- `PGADMIN_DEFAULT_EMAIL` - pgAdmin login
- `PGADMIN_DEFAULT_PASSWORD` - pgAdmin login
- `AIRFLOW_FERNET_KEY` - Airflow secrets encryption (required)
- `AIRFLOW_WEBSERVER_SECRET_KEY` - Airflow web security (required)

**Optional Environment Variables:**
- `REQUEST_TIMEOUT` - HTTP timeout (default: 20s)
- `MAX_RETRIES` - Retry count (default: 3)
- `BACKOFF_FACTOR` - Retry backoff factor (default: 2)
- `LOG_LEVEL` - Logging verbosity (default: INFO)
- `CEREBRAS_API_KEY`, `NVIDIA_API_KEY` - Fallback LLM providers (optional)
- `FUZZY_MATCH_THRESHOLD` - Fuzzy string match threshold (default: 0.90)

**Secrets Location:**
- `.env` file in project root (not version-controlled)
- No integration with external secret management (HashiCorp Vault, AWS Secrets Manager, etc.)

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## Web Scraping & Store Integration

**Scrape Targets:**
- Multiple PC hardware stores with configurable scrape targets stored in database
- Primary implementation: MDComputers (dedicated scraper in `src/scrapers/mdcomputers/scraper.py`)
- Generic scraper framework: `src/scrapers/generic_scraper.py` (supports custom stores via configuration)

**HTTP Client Implementation:**
- Location: `src/scrapers/http_client.py`
- Primary: `curl_cffi` library (if available) for Cloudflare JS challenge bypass via browser impersonation (`impersonate="chrome"`)
- Fallback: Standard `requests` library if `curl_cffi` not installed
- Session-based with configurable timeout and redirect handling

**API Endpoints (FastAPI):**
- Base URL: Typically `http://localhost:8000` (via uvicorn)
- Versioning: All routes under `/api/v1` prefix
- Routes defined in `src/api/routes/`:
  - `stores.py` - Store catalog and configuration
  - `products.py` - Product search, filtering, historical price data
  - `builder.py` - PC build creation with compatibility checks
  - `compare.py` - Multi-product price and spec comparison
  - `images.py` - Product image proxy (restricted to store images; prevents arbitrary URL fetching)
- Static file serving: `src/static/` mounted at `/static`
- Health check: GET `/health`
- Docs: `/docs` (Swagger UI), `/redoc` (ReDoc)

## Data Pipeline Orchestration

**Airflow Integration:**
- Docker service: Apache Airflow 2.9.1 in standalone mode (LocalExecutor)
- Airflow database: Separate PostgreSQL database (`pc_builder_airflow`)
- Web UI: Port `8085` (maps to Airflow's internal port 8080)
- DAGs location: `dags/` directory
- Primary DAG: `dags/scheduled_scraper_dag.py`
  - Scrapes due targets from database
  - Saves search results to database
  - Triggers LLM-based title/spec extraction for CPUs, GPUs, RAM, PSUs, motherboards, coolers, cabinets, monitors
  - Provider chain failover built into extraction service
  - Logs errors per target without stopping entire run
- Secondary DAG: `dags/log_cleanup_dag.py` - Maintenance task

---

*Integration audit: 2026-09-24*
