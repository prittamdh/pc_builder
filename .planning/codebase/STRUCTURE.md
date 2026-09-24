---
last_mapped_commit: a803b6fdb669c9fb39477658b3e08c0a134f8cf2
last_mapped_at: 2026-09-24
---
# Codebase Structure

**Analysis Date:** 2026-09-24

## Directory Layout

```
pc_builder2/
├── dags/                          # Airflow DAG definitions
│   ├── log_cleanup_dag.py          # Housekeeping: trim Airflow logs
│   └── scheduled_scraper_dag.py    # Main pipeline: 15-min scrape, extract, validate
│
├── scripts/                        # Manual maintenance & extraction scripts
│   ├── extract_*_titles_groq.py    # (9 files) LLM identity extraction per category
│   ├── extract_*_specs_groq.py     # (7 files) LLM spec extraction per category
│   ├── populate_*_specs_from_extractions.py # Copy LLM fields to spec tables
│   ├── re_scrape_all_stores.py     # Full re-walk of all category targets
│   ├── repair_unseen_products.py   # Fetch products that pagination missed
│   ├── classify_legacy_products.py # Flag off-policy hardware
│   ├── import_80plus_efficiency.py # Load official PSU ratings
│   └── wire_ram_canonical.py       # Link RAM listings to canonical models
│
├── src/
│   ├── api/
│   │   ├── main.py                 # FastAPI app: CORS, routers, static mount
│   │   ├── deps.py                 # Dependency injection (get_db)
│   │   ├── filters.py              # Common filters: has_usable_price()
│   │   ├── spec_filters.py         # Spec range/enum filters per category
│   │   ├── routes/
│   │   │   ├── products.py         # GET /products, /facets, /{id}/price-series
│   │   │   ├── builder.py          # GET /slots, POST /validate, POST /candidates
│   │   │   ├── compare.py          # POST /compare (multi-store offers)
│   │   │   ├── stores.py           # GET /stores
│   │   │   └── images.py           # GET /images/{id} (proxy for store images)
│   │   └── schemas/
│   │       ├── product.py          # Pydantic: ProductOut, ProductListResponse
│   │       ├── store.py            # Pydantic: StoreOut
│   │       └── price_history.py    # Pydantic: PriceHistoryOut
│   │
│   ├── db/
│   │   ├── base.py                 # SQLAlchemy DeclarativeBase
│   │   ├── connection.py           # Engine setup (database URL parsing)
│   │   ├── session.py              # SessionLocal factory + get_db()
│   │   ├── models/
│   │   │   ├── mixins.py           # TimestampMixin (created_at, updated_at)
│   │   │   ├── store.py            # Store (10 retailers)
│   │   │   ├── product.py          # Product (11,822 listings)
│   │   │   ├── price_history.py    # PriceHistory (append-only)
│   │   │   ├── product_target.py   # Junction: product ↔ scrape_target
│   │   │   ├── scrape_target.py    # ScrapeTarget (123 category URLs)
│   │   │   ├── canonical_part.py   # CanonicalPart (6,815 models)
│   │   │   ├── *_title_extraction.py # (9 files) LLM outputs per category
│   │   │   ├── category_specs.py   # Consolidated: CPU/GPU/Motherboard/etc specs
│   │   │   ├── saved_build.py      # SavedBuild (user's component selections)
│   │   │   └── __init__.py         # ORM model exports
│   │   ├── repositories/
│   │   │   ├── base_repository.py  # BaseRepository (get, create, update, etc.)
│   │   │   ├── product_repository.py # ProductRepository (get_by_sid_pid, etc.)
│   │   │   ├── price_history_repository.py
│   │   │   ├── store_repository.py
│   │   │   ├── scrape_target_repository.py
│   │   │   └── __init__.py
│   │   ├── migrations/
│   │   │   ├── alembic.ini         # Migration config (not in repo, uses env var)
│   │   │   ├── env.py              # Alembic env script
│   │   │   ├── script.py.mako      # Alembic template
│   │   │   └── versions/           # (26 migration files) Schema evolution
│   │   └── __init__.py
│   │
│   ├── scrapers/
│   │   ├── base_scraper.py         # BaseScraper (HTTP client wrapper)
│   │   ├── base_parser.py          # BaseParser (abstract parse methods)
│   │   ├── generic_scraper.py      # GenericScraper (multi-platform support)
│   │   ├── generic_parser.py       # GenericParser (CSS/JSON walk, price/stock/image)
│   │   ├── http_client.py          # HttpClient (curl_cffi fingerprinting, retry logic)
│   │   ├── mdcomputers/
│   │   │   ├── scraper.py          # MDComputers-specific scraper (if needed)
│   │   │   └── parser.py           # MDComputers-specific parser (if needed)
│   │   ├── sites/
│   │   │   ├── pcstudio.py         # PCStudio helpers
│   │   │   ├── primeabgb.py        # PrimeABGB helpers
│   │   │   ├── vedant.py           # Vedant Computers helpers
│   │   │   └── __init__.py
│   │   └── __init__.py
│   │
│   ├── services/
│   │   ├── search_service.py       # Save search results: deduplicate, classify, persist
│   │   ├── scrape_target_service.py # Poll due targets, mark scraped
│   │   ├── store_service.py        # Fetch store config
│   │   ├── product_service.py      # Get products by ID, search, facets
│   │   ├── builder_service.py      # BuilderService (validate, rank, save builds)
│   │   ├── compatibility_engine.py # CompatibilityEngine (socket, RAM, PSU rules)
│   │   ├── compatibility_rules.py  # Rule definitions, wattage estimation, form factors
│   │   ├── comparison_service.py   # Compare prices across stores
│   │   ├── groq_extraction_service.py # LLM API client (Mistral via OpenAI-compat)
│   │   └── __init__.py
│   │
│   ├── matching/
│   │   ├── category_classifier.py  # Assign p_category from title
│   │   ├── legacy_policy.py        # Flag old platforms
│   │   ├── condition_policy.py     # Detect open-box, refurbished, sealed
│   │   ├── canonical_key_builder.py # Build canonical_id from extracted fields
│   │   ├── brand_registry.py       # Known brands per category
│   │   ├── cabinet_clearance.py    # Parse radiator sizes (e.g., "240mm" from title)
│   │   ├── form_factor.py          # Normalize form factors
│   │   ├── motherboard_identity.py # Motherboard-specific extraction logic
│   │   ├── psu_identity.py         # PSU-specific extraction logic
│   │   ├── normalize.py            # Text normalization (lowercase, strip symbols)
│   │   ├── spec_value_normalizer.py # Validate spec bounds
│   │   ├── resolver.py             # Resolve canonical_id conflicts
│   │   ├── matcher.py              # Fuzzy title matching (for legacy fallback)
│   │   ├── scoring.py              # Confidence scoring for extractions
│   │   └── __init__.py
│   │
│   ├── domain/
│   │   ├── base.py                 # BaseModel for domain objects
│   │   ├── search_result.py        # SearchResult (parsed listing before persist)
│   │   ├── product.py              # Product domain object
│   │   ├── price.py                # Price (not used, stub)
│   │   ├── builder.py              # BuildSelection, BuildSummary, etc.
│   │   ├── store.py                # Store domain object
│   │   └── configs/
│   │       ├── scrape_bounds.py    # Field validation ranges (VRAM 1–384, etc.)
│   │       └── spec_bounds.py      # Spec field valid ranges
│   │
│   ├── common/
│   │   ├── logger.py               # Logging config
│   │   ├── constants.py            # Global constants (currencies, categories)
│   │   ├── helpers.py              # Utility functions
│   │   ├── exceptions.py           # Custom exceptions
│   │   ├── retry.py                # Retry decorators
│   │   ├── enums/
│   │   │   ├── target_type.py      # TargetType enum (SEARCH, CATEGORY, etc.)
│   │   │   ├── schedule_type.py    # ScheduleType enum (DAILY, WEEKLY, etc.)
│   │   │   └── __init__.py
│   │   └── __init__.py
│   │
│   ├── configs/
│   │   ├── config.py               # Config class (if using Pydantic settings)
│   │   ├── settings.py             # Global settings from env vars
│   │   └── __init__.py
│   │
│   ├── static/
│   │   ├── index.html              # Entry HTML; mounts app.js
│   │   ├── app.js                  # Main SPA: product search, builder, price chart
│   │   ├── style.css               # Glassmorphic dark-mode stylesheet
│   │   └── index.css               # CSS variables, theme settings
│   │
│   └── __init__.py
│
├── tests/
│   ├── html/                       # Sample HTML fixtures for parser testing
│   │   └── (mock retailer pages)
│   ├── test_*.py                   # Unit/integration tests
│   └── conftest.py                 # Pytest fixtures
│
├── docs/
│   ├── DATAFLOW.md                 # (START HERE) Data pipeline stages 0–7, invariants
│   ├── architecture.md             # (Duplicate of .planning/codebase/ARCHITECTURE.md)
│   ├── canonical_part_resolution_spec.md # Canonical identity extraction design
│   └── competitive_research.md     # Market notes, pricing anomalies
│
├── logs/
│   ├── pc_builder.log              # Main log file
│   ├── dag_id=*/                   # Airflow DAG logs per run
│   └── (Airflow internal logs)
│
├── data/
│   ├── raw/                        # (Git-ignored) Downloaded raw HTML/JSON
│   ├── processed/                  # (Git-ignored) Processed extracts
│   ├── cache/                      # (Git-ignored) HTTP response cache
│   └── exports/                    # (Git-ignored) Export results (CSV, etc.)
│
├── .claude/                        # Claude Code harness
│   ├── settings.json               # Project settings (if any)
│   └── worktrees/                  # Multi-branch development workspaces
│
├── .planning/                      # Planning documents
│   └── codebase/
│       ├── ARCHITECTURE.md         # (This turn's output)
│       └── STRUCTURE.md            # (This turn's output)
│
├── .env                            # (Git-ignored) Environment secrets
├── .env.example                    # (Git-tracked) Env var template
├── .gitignore                      # Exclude logs, data, venv, __pycache__
├── docker-compose.yml              # PostgreSQL + Airflow services
├── Dockerfile                      # Python image for Airflow
├── pyproject.toml                  # Project metadata, dependencies
├── requirements.txt                # Pinned pip requirements (if using)
│
├── README.md                       # Project overview
├── PROGRESS.md                     # Running log of work and bugs
├── PROJECT_MAP.md                  # File-by-file summary (older version)
│
└── project_tree.txt                # (Obsolete) Full directory tree snapshot
```

---

## Directory Purposes

**`dags/`:**
- Purpose: Airflow DAG definitions (pipeline orchestration)
- Contains: Main scrape→extract DAG, log cleanup DAG
- Key files: `scheduled_scraper_dag.py` (15-min cycle)

**`scripts/`:**
- Purpose: Manual maintenance, admin tasks, batch operations
- Contains: LLM extraction runners per category, spec population, legacy flagging, 80 PLUS import
- Key files: `extract_gpu_titles_groq.py`, `populate_specs_from_extractions.py`
- Note: Not run in production DAG; invoked manually or via cron

**`src/api/`:**
- Purpose: REST API layer
- Contains: FastAPI app, route handlers, Pydantic schemas, dependency injection
- Key files: `main.py` (app factory), `routes/products.py` (catalog), `routes/builder.py` (compatibility)
- Entry point: `src/api/main.py::app`

**`src/db/`:**
- Purpose: Data persistence (ORM, migrations, repositories)
- Contains: SQLAlchemy models (20+ tables), Alembic migrations (26+ versions), repository pattern
- Key files: `models/product.py` (listings), `models/canonical_part.py` (models), `session.py` (connection pool)
- Used by: All services and API

**`src/scrapers/`:**
- Purpose: Web scraping (fetch, parse)
- Contains: HTTP client (curl_cffi), CSS/JSON parsers, store-specific helpers
- Key files: `generic_scraper.py`, `generic_parser.py`, `http_client.py`
- Entry point: `GenericScraper(client, store).scrape_category_all_pages()`

**`src/services/`:**
- Purpose: Business logic layer (persist, classify, validate, rank)
- Contains: SearchService (deduplicate & classify), CompatibilityEngine (rules), BuilderService (slot ranking)
- Key files: `search_service.py`, `compatibility_engine.py`, `builder_service.py`

**`src/matching/`:**
- Purpose: Heuristic classification and LLM-driven identity extraction
- Contains: Category classifier, legacy policy, condition detection, canonical key builder
- Key files: `category_classifier.py`, `legacy_policy.py`, `canonical_key_builder.py`

**`src/domain/`:**
- Purpose: Domain models and value objects (before persistence)
- Contains: `SearchResult` (parsed listing), `BuildSelection` (user's build), spec bounds
- Key files: `search_result.py`, `builder.py`

**`src/common/`:**
- Purpose: Shared utilities and configuration
- Contains: Logger, constants, retry decorators, custom exceptions
- Key files: `logger.py`, `settings.py` (from env vars)

**`src/static/`:**
- Purpose: Frontend (single-page app)
- Contains: HTML, vanilla JavaScript, glassmorphic dark-mode CSS
- Key files: `index.html` (page shell), `app.js` (state + API calls), `style.css` (theme)

**`tests/`:**
- Purpose: Unit and integration tests
- Contains: Parser tests (mocked retailer HTML), service tests, API endpoint tests
- Key files: `conftest.py` (fixtures), `test_*.py` (test modules)

**`docs/`:**
- Purpose: Documentation and reference
- Key files: `DATAFLOW.md` (read first!), `canonical_part_resolution_spec.md`, `competitive_research.md`

---

## Key File Locations

**Entry Points:**

| Purpose | File | Role |
|---------|------|------|
| DAG orchestration | `dags/scheduled_scraper_dag.py` | Airflow scheduler invokes every 15 min |
| REST API | `src/api/main.py::app` | FastAPI application; CORS, routers, static files |
| Web UI | `src/static/index.html` | SPA entry; loads app.js |
| Database setup | `src/db/session.py::SessionLocal` | ORM session factory |

**Configuration:**

| Purpose | File |
|---------|------|
| Env vars | `src/configs/settings.py` (reads from `.env`) |
| Database URL | `src/configs/settings.py::DATABASE_URL` |
| Retry logic | `src/common/retry.py` |
| Request headers | `src/configs/settings.py::DEFAULT_HEADERS` |

**Core Logic:**

| Purpose | File |
|---------|------|
| Scrape & parse | `src/scrapers/generic_scraper.py`, `src/scrapers/generic_parser.py` |
| Persist & classify | `src/services/search_service.py` |
| Compatibility check | `src/services/compatibility_engine.py` |
| Category assignment | `src/matching/category_classifier.py` |
| Legacy flagging | `src/matching/legacy_policy.py` |
| LLM extraction | `scripts/extract_*_titles_groq.py` (9 per category) |

**Testing:**

| Purpose | File |
|---------|------|
| Parser tests | `tests/test_parser.py` (if exists) |
| API tests | `tests/test_routes.py` (if exists) |
| Fixtures | `tests/conftest.py`, `tests/html/` (mock retailer pages) |

---

## Naming Conventions

**Files:**

- **Modules**: `snake_case.py` (e.g., `search_service.py`, `category_classifier.py`)
- **Classes**: `PascalCase` (e.g., `SearchService`, `GenericScraper`)
- **Functions**: `snake_case` (e.g., `execute_due_scrape_targets()`)
- **Constants**: `UPPER_CASE` (e.g., `REQUEST_TIMEOUT`, `SORT_OPTIONS`)
- **Tests**: `test_*.py` or `*_test.py` (e.g., `test_parser.py`)
- **Alembic migrations**: `<uuid>_<description>.py` (auto-generated)

**Directories:**

- **Package modules**: Lowercase, underscore-separated (e.g., `src/db/`, `src/services/`, `src/matching/`)
- **Feature bundles**: Group by responsibility (e.g., all database code in `src/db/`, all scraping in `src/scrapers/`)
- **Scripts**: Descriptive, action-oriented (e.g., `extract_gpu_titles_groq.py`, `repair_unseen_products.py`)

**Database:**

- **Tables**: Plural, snake_case (e.g., `products`, `price_history`, `gpu_title_extractions`)
- **Columns**: snake_case (e.g., `current_price`, `canonical_id`, `spec_status`)
- **Primary keys**: `id` (auto-increment)
- **Foreign keys**: `<table_singular>_id` (e.g., `product_id`, `store_id`)
- **Unique constraints**: `uq_<table>_<cols>` (e.g., `uq_products_sid_pid`)

---

## Where to Add New Code

**New Feature (e.g., CPU compatibility checker enhancement):**
- Primary code: `src/services/compatibility_engine.py` or `src/services/compatibility_rules.py`
- Tests: `tests/test_compatibility_engine.py` (if not exists, create it)
- Configuration: Add bounds/rules to `src/domain/configs/scrape_bounds.py` if needed
- Migration: If database schema changes, create new migration via `alembic revision --autogenerate -m "description"`

**New Component/Module (e.g., new scraper for a retailer):**
- Scraper: `src/scrapers/{retailer_name}/scraper.py`
- Parser: `src/scrapers/{retailer_name}/parser.py` (or add to `generic_parser.py` if generic platform)
- Store config: Insert row into `stores` table (no code changes needed; config lives in DB)
- Tests: `tests/test_scrapers.py` (or `tests/{retailer_name}/`)

**New API Endpoint (e.g., GET /trending):**
- Route: New method in `src/api/routes/products.py` (or create `src/api/routes/trending.py`)
- Schema: Add Pydantic model to `src/api/schemas/product.py`
- Service: Use existing `ProductService` or create new `TrendingService` in `src/services/`
- Register: Add `app.include_router(router, prefix="/api/v1")` in `src/api/main.py`
- Tests: `tests/test_api_routes.py`

**New Maintenance Script (e.g., detect price anomalies):**
- Location: `scripts/detect_price_anomalies.py`
- Pattern: Take argv inputs, use `SessionLocal()` for DB access, print results to stdout/log
- Run: User invokes manually or schedules with cron (not in DAG)
- Example: See `scripts/repair_unseen_products.py`, `scripts/classify_legacy_products.py`

**Utilities and Helpers:**
- Shared across services: `src/common/helpers.py`
- Matching-specific: `src/matching/{new_module}.py`
- Retry/HTTP logic: `src/common/retry.py`

**Deployment & Config:**
- Environment-specific `.env` file (git-ignored; see `.env.example`)
- Docker Compose: `docker-compose.yml` (PostgreSQL + Airflow)
- Alembic: Migrations auto-run on container startup

---

## Special Directories

**`data/`:**
- Purpose: Temporary storage (downloads, caches, exports)
- Generated: Yes (populated by scripts and API)
- Committed: No (git-ignored via `.gitignore`)
- Subdirs: `raw/` (raw HTML/JSON), `processed/` (cleaned data), `cache/` (HTTP caches), `exports/` (CSV, etc.)

**`logs/`:**
- Purpose: Runtime logs
- Generated: Yes (Airflow task logs, app logs)
- Committed: No (git-ignored)
- Files: `pc_builder.log` (main app), `dag_id=*/` (Airflow per-DAG)

**`.planning/codebase/`:**
- Purpose: GSD orchestrator planning documents
- Generated: Yes (by `/gsd:map-codebase` and related skills)
- Committed: Yes (review before merging)
- Contents: `ARCHITECTURE.md`, `STRUCTURE.md`, `CONVENTIONS.md`, `TESTING.md`, `CONCERNS.md`, `STACK.md`, `INTEGRATIONS.md`

**`db/migrations/versions/`:**
- Purpose: Alembic schema evolution history
- Generated: Yes (by `alembic revision`)
- Committed: Yes (full history tracked)
- Format: UUID + descriptive filename (e.g., `6b3dbe4850ce_initial_schema.py`)

---

## Product and Price Identities

### Listing (per-store, per-price):

| Field | Table | Key | Example |
|-------|-------|-----|---------|
| Listing ID | `products` | `(sid, pid)` | `(1, "rtx-5080-asus-tuf")` at MDComputers |
| Price | `products` | `current_price` | 1,89,999 INR |
| Store | `products` | `sid` (FK → `stores.id`) | 1 (MDComputers) |
| Product URL | `products` | `product_url` | `mdcomputers.in/product/...` |

### Model (cross-store, per-product):

| Field | Table | Key | Example |
|-------|-------|-----|---------|
| Model ID | `canonical_parts` | `canonical_id` | `gpu:asus:rtx_5080:tuf_gaming_oc` |
| Specs | `gpu_specs` | `canonical_id` | VRAM: 16GB, TDP: 320W, length: 267mm |
| Extraction | `gpu_title_extractions` | `canonical_id` | Brand: ASUS, Model: RTX 5080, Variant: TUF Gaming OC |

**Join:** `products.canonical_id` → `canonical_parts.canonical_id` → `gpu_specs.canonical_id`

---

*Structure analysis: 2026-09-24*
