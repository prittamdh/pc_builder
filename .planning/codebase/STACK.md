---
last_mapped_commit: a803b6fdb669c9fb39477658b3e08c0a134f8cf2
last_mapped_at: 2026-09-24
---
# Technology Stack

**Analysis Date:** 2026-09-24

## Languages

**Primary:**
- Python 3.12+ - Main application language for API, scrapers, data processing, and data pipeline
- Python 3.11 - Airflow Docker image runtime (Apache Airflow 2.9.1)

## Runtime

**Environment:**
- Python 3.12+ (local development and primary application)
- Docker containers for PostgreSQL 15, pgAdmin, and Apache Airflow

**Package Manager:**
- pip (from requirements.txt)
- No lock file present; dependencies specified with minimum version constraints

## Frameworks

**Core:**
- FastAPI 0.115.0+ - REST API framework with automatic OpenAPI docs
- uvicorn 0.30.0+ - ASGI web server for FastAPI application

**Data Processing & ORM:**
- SQLAlchemy 2.0.0+ - SQL toolkit and ORM for database interactions
- Alembic 1.16+ - Database migration tool

**Task Scheduling & Orchestration:**
- Apache Airflow 2.9.1 - Workflow orchestration and DAG scheduling (LocalExecutor mode)

**Testing:**
- pytest 8.4.0+ - Unit and integration testing framework

**Web Scraping:**
- BeautifulSoup4 4.13.0+ - HTML parsing and extraction
- lxml 6.0.0+ - XML/HTML processing backend
- curl_cffi (optional, see `src/scrapers/http_client.py`) - Cloudflare bypass via browser impersonation

## Key Dependencies

**Critical:**
- SQLAlchemy 2.0.0+ - Async-capable ORM, declarative base, type-hinted queries (`src/db/connection.py`, `src/db/session.py`)
- psycopg[binary] 3.2.0+ - PostgreSQL adapter for Python; dual protocol support (psycopg3 and fallback to psycopg2 for SQLAlchemy 1.4 compat)
- Pydantic 2.11.0+ - Data validation and serialization (all domain models in `src/domain/`, API schemas in `src/api/schemas/`)
- tenacity 9.1.0+ - Retry decorator for resilience in scrapers and LLM calls

**Infrastructure & HTTP:**
- requests 2.32.0+ - Standard HTTP client library (web scraping fallback)
- httpx 0.28.0+ - Async HTTP client (used in `src/api/routes/images.py`, `src/services/groq_extraction_service.py`)

**Configuration:**
- PyYAML 6.0.2+ - YAML parsing and serialization
- python-dotenv 1.1.0+ - Environment variable loading from `.env`

**Data Processing:**
- openpyxl 3.1.0+ - Excel file reading (80 PLUS efficiency certification import in `scripts/import_80plus_efficiency.py`)

## Configuration

**Environment:**
- `.env` file in project root (not committed; contains secrets)
- `src/configs/settings.py` loads all configuration from environment variables via `python-dotenv`

**Key Environment Variables:**
- `DATABASE_URL` - PostgreSQL connection string (defaults to `postgresql+psycopg://pc_builder:pc_builder123@localhost:5432/pc_builder`)
- `REQUEST_TIMEOUT` - HTTP request timeout in seconds (default: 20)
- `MAX_RETRIES` - Retry attempts for requests (default: 3)
- `BACKOFF_FACTOR` - Exponential backoff factor for retries (default: 2)
- `LOG_LEVEL` - Logging level (default: INFO)
- `GROQ_API_KEY` - Groq LLM API authentication
- `MISTRAL_API_KEY` - Mistral LLM API authentication
- `GOOGLE_API_KEY` - Google Gemini API authentication
- `CEREBRAS_API_KEY` - Cerebras LLM API authentication
- `NVIDIA_API_KEY` - NVIDIA NIM API authentication
- `FUZZY_MATCH_THRESHOLD` - Fuzzy string matching threshold (default: 0.90)
- `POSTGRES_PASSWORD` - PostgreSQL password (Docker)
- `PGADMIN_DEFAULT_EMAIL` - pgAdmin login email
- `PGADMIN_DEFAULT_PASSWORD` - pgAdmin login password
- `AIRFLOW_FERNET_KEY` - Airflow encryption key for sensitive data
- `AIRFLOW_WEBSERVER_SECRET_KEY` - Airflow web UI secret key

**Build:**
- `pyproject.toml` - Project metadata and build configuration (setuptools-based)
- Tests configured with pytest (`testpaths = ["tests"]`)

## Platform Requirements

**Development:**
- Python 3.12+ interpreter
- pip package manager
- PostgreSQL 15 (via Docker Compose recommended)
- Docker & Docker Compose (for local database, pgAdmin, Airflow)

**Production:**
- Python 3.12+ runtime
- PostgreSQL 15 database
- Apache Airflow 2.9.1+ orchestration service
- Web server capable of running ASGI applications (Gunicorn + uvicorn recommended)

## Architecture Notes

**API Startup:**
- FastAPI app instantiated in `src/api/main.py`
- Serves static UI from `src/static/`
- CORS enabled for all origins, all methods
- Health check endpoint at `/health`
- API routes versioned under `/api/v1` prefix

**Database:**
- Connection pooling via SQLAlchemy (pool_pre_ping enabled for stability)
- Docker host fallback: `localhost:5432` → `postgres:5432` when running in container
- Migrations managed by Alembic (`src/db/migrations/versions/`)

**Data Pipeline:**
- Airflow DAGs in `dags/` directory
- Primary DAG: `scheduled_scraper_dag.py` - runs web scraping and LLM-based entity extraction
- Log cleanup DAG: `log_cleanup_dag.py`
- Extraction scripts in `scripts/` for each PC component category (CPU, GPU, RAM, PSU, motherboard, etc.)

---

*Stack analysis: 2026-09-24*
