---
last_mapped_commit: a803b6fdb669c9fb39477658b3e08c0a134f8cf2
last_mapped_at: 2026-09-24
---
<!-- refreshed: 2026-09-24 -->

# Architecture

**Analysis Date:** 2026-09-24

## System Overview

PC Builder 2 is a multi-stage product scraping, identity normalization, and compatibility engine that aggregates PC hardware across 10 Indian retailers, extracts specifications via LLM, and validates hardware compatibility. The system separates two distinct identities: **listings** (per-store, per-price) and **models** (cross-store, per-product identity).

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         Scrape Orchestration (Airflow DAG)           │
│              `dags/scheduled_scraper_dag.py`                         │
│   Polls every 15 min: due targets → scrape → parse → persist       │
└───────────────────────────────────────┬─────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Stage 0: Configuration                       │
│  Stores + Scrape Targets (selector paths, endpoints, limits)        │
│              `src/services/scrape_target_service.py`                │
└───────────────────────────────────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────┬──────────────────────┬──────────────────────┐
│  Stage 1: Scrape     │  Stage 2: Parse      │  Stage 3: Persist   │
│  `GenericScraper`    │  `GenericParser`     │  `SearchService`    │
│  `src/scrapers/`     │  `src/scrapers/`     │  `src/services/`    │
│  curl_cffi / HTTP    │  BeautifulSoup4      │  Format + classify  │
│  Multi-store sync    │  Selector walk       │  Deduplicate        │
└──────────────────────┴──────────────────────┴──────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Database: Listings + Prices                      │
│        `products` (11,822 rows) + `price_history` (append-only)    │
│               `sid`, `pid` = store ID + store-specific ID           │
│                     Per-listing price, stock, URL, image            │
└───────────────────────────────────────┬─────────────────────────────┘
         │
         ├──────────────────────────────────────────────────────────┐
         │                                                          │
         ▼                                                          ▼
┌──────────────────────────────────────┐    ┌──────────────────────────┐
│  Stage 4: LLM Identity Extraction    │    │  Classify + Legacy Flag  │
│  `GroqExtractionService` (Mistral)   │    │  `CategoryClassifier`    │
│  `scripts/extract_*_titles_groq.py`  │    │  `legacy_policy.py`      │
│  ↓                                    │    │  `condition_policy.py`   │
│  Canonical parts + model identity    │    │  Mark old/sealed/open    │
│  (`canonical_id`, spec fields)       │    └──────────────────────────┘
└──────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 Database: Models + Canonical Identity               │
│  `canonical_parts` (6,815 rows) + 9 × `*_specs` tables             │
│                    `canonical_id` = key across all stores           │
│                    Sockets, wattage, VRAM, form factors, etc.       │
└───────────────────────────────────────┬─────────────────────────────┘
         │
         ├──────────────────────────────────────────────────────────┐
         │                                                          │
         ▼                                                          ▼
┌──────────────────────────────────────┐    ┌──────────────────────────┐
│          FastAPI Read Endpoints      │    │   Compatibility Engine   │
│  `src/api/routes/`                   │    │  `CompatibilityEngine`   │
│  ├─ /products → catalog search       │    │  Validates socket, RAM,  │
│  ├─ /products/facets → filters       │    │  PSU wattage, cabinet    │
│  ├─ /builder/validate → build check  │    │  form factor, etc.       │
│  ├─ /builder/candidates → filtered   │    │  Order-independent rules │
│  ├─ /compare → multi-store offers    │    │  (same rules, any order) │
│  └─ /products/{id}/price-series     │    └──────────────────────────┘
└──────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│           Glassmorphic Web UI (Static HTML + JavaScript)            │
│                 `src/static/` (index.html, app.js)                  │
│            Client-side routing, real-time build validation          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **Scrape Orchestration** | Schedule, poll, and invoke scrape targets every 15 min | `dags/scheduled_scraper_dag.py` |
| **Scraper** | Fetch URLs via curl_cffi, handle pagination, store-specific auth | `src/scrapers/generic_scraper.py` |
| **Parser** | CSS selector walk / JSON walk; extract price, name, image, stock | `src/scrapers/generic_parser.py` |
| **SearchService** | Deduplicate, classify, upsert products, append price history | `src/services/search_service.py` |
| **CategoryClassifier** | Assign `p_category` from title or store raw category | `src/matching/category_classifier.py` |
| **LLM Extraction** | Call Mistral to extract brand, model, specs from titles | `src/services/groq_extraction_service.py` |
| **Compatibility Engine** | Validate socket, RAM, PSU wattage, cabinet fit; merge specs/LLM | `src/services/compatibility_engine.py` |
| **API Layer** | REST endpoints: catalog search, builder validation, price history | `src/api/routes/` |
| **Persistence** | SQLAlchemy ORM, Alembic migrations, repository pattern | `src/db/` |
| **UI** | Single-page app: product search, PC builder, price chart | `src/static/` |

---

## Pattern Overview

**Overall:** **Multi-stage scrape-to-serve pipeline** with **LLM-driven identity extraction**, **separation of listing identity from model identity**, and **read-only compatibility rules** that apply regardless of build order.

**Key Characteristics:**
- **Separation of concerns**: Scrape → Parse → Classify → Extract → Validate → Serve
- **Immutable price history**: Append-only `price_history` table; never overwrite past prices
- **Dual identity model**: `(sid, pid)` for listings (store-specific), `canonical_id` for models (cross-store)
- **LLM-as-source-of-truth**: Mistral extraction prefered over regex-derived `*_specs`; `*_title_extractions` feed the builder
- **Order-independent compatibility**: Rules check pairwise/aggregate relationships, not pick sequence
- **Legacy/condition tracking**: Flag old parts and open-box stock; don't delete, just hide
- **Incremental processing**: DAG runs every 15 min; extractors process only missing `canonical_id` rows

---

## Layers

**Orchestration Layer** (`dags/scheduled_scraper_dag.py`):
- Purpose: Coordinate all pipeline stages on a 15-min schedule
- Location: `dags/scheduled_scraper_dag.py`
- Contains: Airflow DAG task definitions; invokes scraper, classifier, LLM, and spec extractors
- Depends on: Airflow 2.9.1, all downstream services
- Used by: Apache Airflow scheduler

**Scrape Layer** (`src/scrapers/`):
- Purpose: Fetch and parse retailer pages
- Location: `src/scrapers/generic_scraper.py`, `src/scrapers/generic_parser.py`
- Contains: HTTP client wrapper, CSS selector / JSON walking, platform-specific parsers
- Depends on: `curl_cffi` (fingerprinting bypass), `BeautifulSoup4`, store configuration
- Used by: DAG → `execute_due_scrape_targets()`

**Service Layer** (`src/services/`):
- Purpose: Business logic: persist search results, classify categories, validate compatibility, rank candidates
- Location: `src/services/search_service.py`, `src/services/compatibility_engine.py`, `src/services/builder_service.py`
- Contains: Repository access, classification, LLM calls, rule evaluation
- Depends on: Database session, domain models, matching/classification modules
- Used by: DAG, API endpoints

**Matching/Extraction Layer** (`src/matching/`, LLM scripts):
- Purpose: Category classification, legacy policy, canonical key building, spec normalization
- Location: `src/matching/category_classifier.py`, `src/matching/legacy_policy.py`, `src/matching/canonical_key_builder.py`, `scripts/extract_*_titles_groq.py`
- Contains: Heuristic classifiers, regex anchors, Mistral API calls, field validation
- Depends on: Product title, store category, spec bounds, LLM API keys
- Used by: SearchService, DAG → canonical extraction tasks

**Data Access Layer** (`src/db/`):
- Purpose: ORM models, repositories, session management
- Location: `src/db/models/`, `src/db/repositories/`, `src/db/session.py`
- Contains: SQLAlchemy models for all tables, base repository pattern, connection pool
- Depends on: PostgreSQL 15, SQLAlchemy 2.0+, Alembic migrations
- Used by: Services and API

**API Layer** (`src/api/`):
- Purpose: FastAPI REST endpoints for catalog, builder, compare, price history
- Location: `src/api/main.py`, `src/api/routes/`
- Contains: Request/response schemas, filtering, sorting, dependency injection
- Depends on: Data access layer, compatibility engine
- Used by: Glassmorphic UI, external integrations

**UI Layer** (`src/static/`):
- Purpose: Single-page app for browsing, filtering, building, and price tracking
- Location: `src/static/index.html`, `src/static/app.js`
- Contains: HTML structure, Vanilla JS (no framework), real-time API calls, state management
- Depends on: FastAPI backend
- Used by: End users

---

## Data Flow

### Primary Request Path: Scrape & Persist

1. **DAG Trigger** (`dags/scheduled_scraper_dag.py`: `execute_due_scrape_targets()`)
   - Polls `scrape_targets` for entries where `next_scrape_at <= now`
   - Limit: 10 targets per run to avoid overwhelming stores

2. **Scrape** (`src/scrapers/generic_scraper.py`: `scrape_category_all_pages()`)
   - Fetch category URL (or search query) via `curl_cffi` with antibot headers
   - Follow pagination, deduplicate by `pid` to avoid repeats across pages
   - Stop on empty page or max_pages limit (default: 2)

3. **Parse** (`src/scrapers/generic_parser.py`: `parse_search()`)
   - Dispatch by store (special case for Computech, ModX, Shopify, FleetCart) or generic CSS selector walk
   - Extract: title (prefer `title`/`aria-label` attributes), price (first money-looking amount), image, stock status
   - Return list of `SearchResult` domain objects (not yet persisted)

4. **Deduplicate & Classify** (`src/services/search_service.py`: `save_many()`)
   - Group by `(sid, pid)` to remove duplicates within a scrape
   - For each result:
     - Call `CategoryClassifier.get_p_category()` (prefer store raw category, override from title if mismatch)
     - Call `detect_condition()` to mark open-box / refurbished / sealed
     - Upsert `products` on `(sid, pid)` unique constraint
     - If name or category changed, reset `spec_status='pending'` (invalidate old extraction)

5. **Persist & Record** (`src/services/search_service.py`: `save()`)
   - Insert/update `products` row
   - **Always append** a `price_history` row (even if price unchanged)
   - Link `product_targets` (which scrape target found which product)

6. **Mark Target Done** (`src/services/scrape_target_service.py`: `mark_scraped()`)
   - Update `scrape_targets.next_scrape_at = now + schedule_config['interval']`

### Secondary Flow: LLM Identity Extraction

1. **DAG Trigger** (`dags/scheduled_scraper_dag.py`: `execute_canonical_extraction()`)
   - Import each category's `extract_*_identity()` function (e.g., `extract_gpu_identity()`)
   - Call with `limit=15` (per category, per DAG run)

2. **Incremental Extraction** (`scripts/extract_gpu_titles_groq.py`: `extract_gpu_identity()`)
   - Query `products` WHERE `p_category='GPU'` AND (`canonical_id IS NULL` OR `spec_status='pending'`)
   - For each row, call Mistral API with few-shot prompt (brand, model, VRAM, TDP, chipset, etc.)
   - Insert/upsert `gpu_title_extractions` row
   - Compute canonical key from extracted fields: `gpu:brand:model:variant` (e.g., `gpu:asus:rtx_5080:tuf_gaming_oc`)
   - Insert/upsert `canonical_parts` row
   - Update `products.canonical_id` and `spec_status='extracted'` or `'needs_review'`

3. **Spec Extraction** (`scripts/populate_specs_from_extractions.py`: Stage 2)
   - Query `*_title_extractions` WHERE no corresponding `*_specs` row exists
   - Copy LLM fields (e.g., `gpu_title_extractions.vram` → `gpu_specs.vram`)
   - Validate against `BOUNDS` (e.g., VRAM must be 1–384 GB); leave NULL if impossible
   - Insert `*_specs` row; link to `canonical_parts` via `canonical_id`

---

## Key Abstractions

**SearchResult** (domain object, `src/domain/search_result.py`):
- Purpose: Immutable container for one parsed listing before persistence
- Fields: `sid`, `pid`, `name`, `url`, `price`, `mrp`, `image`, `in_stock`, `store`
- Used by: Parser → SearchService

**Product** (ORM model, `src/db/models/product.py`):
- Purpose: One row per listing (store × product ID)
- Unique constraint: `(sid, pid)`
- Key fields: `canonical_id` (nullable, reference to model), `p_category`, `current_price`, `in_stock`, `spec_status`, `is_legacy`, `condition`

**PriceHistory** (ORM model, append-only, `src/db/models/price_history.py`):
- Purpose: Immutable log of every price seen at every scrape
- Keyed by: `product_id` + `scraped_at`
- Used by: `/products/{id}/price-series` endpoint, `repair_unseen_products.py`

**CanonicalPart** (ORM model, `src/db/models/canonical_part.py`):
- Purpose: One row per product model across all stores
- Keyed by: `canonical_id` (e.g., `gpu:asus:rtx_5080:tuf_gaming_oc`)
- References: All `*_title_extractions` and `*_specs` rows for that model

**\*TitleExtraction** (e.g., `GPUTitleExtraction`, 9 tables total):
- Purpose: LLM-extracted identity and spec fields per listing
- Keyed by: `product_id` (FK → `products.id`) and `canonical_id` (FK → `canonical_parts`)
- Used by: Builder (preferred source over `*_specs`), compatibility engine, API

**\*Specs** (e.g., `GPUSpecs`, 9 tables total):
- Purpose: Normalized physical specs per model (currently regex-derived, soon curated external data)
- Keyed by: `canonical_id` (FK → `canonical_parts`)
- Used by: Compatibility engine (fallback if LLM extraction missing), API spec filters

---

## Entry Points

**Scrape Orchestration Entry**:
- Location: `dags/scheduled_scraper_dag.py`
- Triggers: Airflow scheduler every 15 min
- Responsibilities: Poll due targets, invoke scraper, classify, extract, validate, mark done

**API Entry**:
- Location: `src/api/main.py::app`
- Triggers: HTTP requests to `http://localhost:8000/api/v1/...`
- Responsibilities: Authenticate session, validate query params, fetch/filter data, return JSON

**UI Entry**:
- Location: `src/static/index.html`
- Triggers: Browser load or deep link
- Responsibilities: Initialize state, fetch initial data, render UI, handle user events

**Manual Maintenance Scripts**:
- Location: `scripts/`
- Triggers: User invocation (usually cron or ad-hoc)
- Responsibilities: Re-scrape all stores, repair unseen products, import 80 PLUS registry, classify legacy

---

## Architectural Constraints

- **Dual identity immutability**: Once a listing is saved with `(sid, pid)`, that pair is never deleted (price history survives). `canonical_id` may be NULL initially, then populated via LLM.
- **Price history append-only**: Every scrape appends a `price_history` row; `products.updated_at` reflects only schema changes, not price changes. This is the source of truth for "was this product seen?".
- **LLM-driven identity**: Mistral extraction is the canonical source; `*_specs` is a fallback. Flip the priority if external curated specs become available.
- **No global state**: No module-level singletons; all state lives in the database. HTTP client, LLM client, and DB session are created per request/task.
- **Airflow orchestration**: All scrape/extract tasks run via DAG; no manual scripts in production (scripts are for maintenance/ad-hoc).
- **Single-store prices**: Price sorting and cost estimates always use the cheapest option per model across all stores; no averaging.
- **Spec per model**: Socket, wattage, VRAM are properties of the model, not the listing. A spec belongs to `canonical_id`, not `product_id`.
- **PostgreSQL as source of truth**: All state (products, prices, extractions, builds, stores) lives in PostgreSQL. No caching layer.

---

## Anti-Patterns

### MRP-Based Ranking

**What happens:** Sorting by discount (`mrp - price`) or ranking results by discount ratio.

**Why it's wrong:** Indian retailers inflate MRP to manufacture headline discounts. The cheapest listings under this metric are often the least honest ones.

**Do this instead:** Sort by `price` only (either ascending or descending). Let users filter by store if they trust a specific retailer. See `src/api/routes/products.py`: `SORT_OPTIONS`.

### Store-Averaged Specs

**What happens:** Averaging a per-listing value (e.g., PSU wattage or RAM speed) across stores and presenting the average as a model property.

**Why it's wrong:** Specs are per-model, not per-listing. A spec tells you about the product itself; a listing tells you where to buy it. Averaging erases information.

**Do this instead:** Specs live in `*_specs` tables keyed by `canonical_id`. Prices are in `products` keyed by `(sid, pid)`. Never join a price value across a spec.

### Deleting Legacy or Out-of-Stock

**What happens:** Removing `products` rows for old platforms (pre-10th-gen Intel) or out-of-stock listings.

**Why it's wrong:** Price history is lost. Future users can't see why a product was popular in 2024 but isn't today.

**Do this instead:** Flag with `is_legacy=true` or hide by default; keep the row and all price history. See `src/matching/legacy_policy.py`.

### Unanchored Regex Over Large Text

**What happens:** Running a regex pattern like `r"\d+GB"` over an entire product card's HTML without anchors.

**Why it's wrong:** The pattern matches unrelated numbers in metadata, comments, or other fields. A soundbar with "80" in its SKU got matched as "80 GB RAM" once.

**Do this instead:** Anchor patterns to specific elements: `element.get("title")` or `element.find("span", class_="capacity").text`. See `src/scrapers/generic_parser.py`: helpers like `_clean_price()`.

---

## Error Handling

**Strategy:** Fail fast per target, but don't sink the entire DAG run. Log every error; only raise if all targets failed.

**Patterns:**

- **Per-target try/except** (`dags/scheduled_scraper_dag.py`: `execute_due_scrape_targets()`): Each target is scraped in a try/except; failure logs and increments a counter. If `failed == attempted`, raise `RuntimeError`.
  
- **Parse failures are non-fatal** (`src/scrapers/generic_scraper.py`: `scrape_search_all_pages()`): If a page parse fails (exception caught), skip that page and continue pagination. Stop if no new results.
  
- **LLM rate limits**: Mistral free tier is ~50 req/min. The DAG limits extraction to 15 per category per run (~9 categories × 15 = 135 req/run, runs every 15 min = ~9 req/min average). If rate-limited, the extraction task logs and continues on the next DAG cycle.
  
- **Missing required fields**: Never invent values. If a selector returns empty, leave the field NULL and skip the product (or mark it in `price_history.in_stock=false`). See invariant #2 in DATAFLOW.md.
  
- **Database session rollback**: If a SearchService.save() fails within a batch, the entire batch rolls back; no partial insert. See `src/services/search_service.py`: `save_many()` followed by `commit()`.

---

## Cross-Cutting Concerns

**Logging:**
- Framework: Python `logging` module
- Locations: `src/common/logger.py` (module-level config), prints to `logs/pc_builder.log`
- Pattern: Every scrape target logs start/finish; every API request logs GET/POST with path; every LLM call logs category + row count

**Validation:**
- Framework: Pydantic v2 (domain objects) + SQLAlchemy constraints (database)
- Pattern: `SearchResult` validates `price >= 0`, `url` is HTTP(S), `in_stock` is bool. `Product` unique constraint on `(sid, pid)`. Specs validated against `BOUNDS` before insert.
- Example: `src/domain/search_result.py`: `@model_validator` fills defaults for `pid` from URL path; `src/api/routes/products.py`: `min_price`, `max_price` as decimal Query params.

**Authentication:**
- Framework: None (single-user admin tool, deployed locally or behind auth proxy)
- Pattern: Trust all HTTP clients; no JWT or session tokens
- Recommendation for production: Add CORS origin whitelist, session middleware, or API key validation

---

*Architecture analysis: 2026-09-24*
