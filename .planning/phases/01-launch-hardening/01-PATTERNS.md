# Phase 1: Launch Hardening - Pattern Map

**Mapped:** 2026-09-24
**Files analyzed:** 24 (new + modified, across 01-01..01-04)
**Analogs found:** 22 / 24

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `src/api/main.py` (CORS, headers, limiter, docs toggle) | config/middleware | request-response | `src/api/main.py` (itself, current state) | exact (in-place change) |
| `src/api/main.py` (404/500 handlers) | controller | request-response | `src/api/main.py:38-40` `serve_index()` (FileResponse pattern) | role-match |
| `src/configs/settings.py` (ENV, remove default DB URL) | config | CRUD (env read) | `src/configs/settings.py` (itself) | exact (in-place change) |
| `src/api/routes/builder.py` (>20 ids, body-size dep on `save_build`) | controller/route | request-response | `src/api/routes/builder.py:244-252` (existing unknown-ids check in the same function) | exact |
| `src/api/routes/images.py` (tests only; logic already correct) | route | file-I/O / streaming | `src/api/routes/images.py` (itself) | exact |
| `.env.example` | config | file-I/O | `docker-compose.yml` env blocks + `src/configs/settings.py` (source of truth for var names) | role-match |
| `tests/test_cors.py` (new) | test | request-response | `tests/test_image_proxy.py` (TestClient-free unit style) + `tests/test_frontend_e2e.py` fixture (`base_url`, subprocess-boot pattern) | role-match |
| `tests/test_settings.py` (new) | test | CRUD (env read) | `tests/test_price_freshness.py` (pure-function unit style, `sys.path.insert` pattern) | role-match |
| `tests/test_rate_limits.py` (new) | test | request-response | `tests/test_frontend_e2e.py` (`base_url` subprocess-boot fixture, for a real TestClient/live-server test) | role-match |
| `tests/test_security_headers.py` (new) | test | request-response | `tests/test_image_proxy.py` (plain function-call unit test style) | role-match |
| `tests/test_docs_disabled.py` (new) | test | request-response | `tests/test_settings.py`-shape (env-var override + import) | role-match (no exact analog; new pattern) |
| `tests/test_builder_validation.py` (new) | test | request-response | `tests/test_compatibility_rules.py` (imports the module under test directly, asserts behavior) | role-match |
| `tests/test_env_example.py` (new) | test | file-I/O | `tests/test_price_freshness.py` (pure parse/diff, no DB) | role-match |
| `src/static/404.html`, `500.html` (new) | component (static HTML) | request-response | `src/static/index.html` (existing static HTML served via `FileResponse`) | role-match |
| `src/static/about.html`, `privacy.html` (new) | component (static HTML) | request-response | `src/static/index.html` (head/meta/footer structure) | role-match |
| `src/static/index.html` (head meta/OG/canonical/favicon, footer links) | component | request-response | itself, lines 1-8 (head) and 172-183 (footer) | exact (in-place change) |
| `tests/test_frontend_e2e.py` (375px viewport flow) | test | event-driven (browser) | itself, lines 1-78 (fixtures: `base_url`, `browser`, `page`) | exact (extend existing) |
| `tests/test_error_pages.py` (new) | test | request-response | `tests/test_frontend_e2e.py`'s `base_url` fixture (needs a live app) or plain `TestClient` (see main.py's routers) | role-match |
| `tests/test_seo_basics.py` (new) | test | request-response | `tests/test_error_pages.py`-shape / `tests/test_image_proxy.py` style | role-match (new pattern) |
| `src/services/compatibility_engine.py` (`_eval_rule` third state, `product_name`, wattage naming) | service | transform | itself, lines 221-238 (`_eval_rule`), 262-283 (wattage aggregate) | exact (in-place change) |
| `src/domain/builder.py` (`CompatibilityWarning.level`, `BuildSummary` fields) | model (Pydantic schema) | transform | itself, lines 20-37 | exact (in-place change) |
| `src/static/app.js` (3-state verdict, wattage notes) | component | transform/render | itself, lines 789-806 | exact (in-place change) |
| `dags/scheduled_scraper_dag.py` (per-store freshness, `check_extraction_progress`) | service (pure function) + orchestration wiring | batch/event-driven | itself, lines 238-260 (`check_price_freshness`/`price_data_is_stale`), 313-324 (task wiring) | exact (in-place change) |
| `tests/test_price_freshness.py` (per-store cases) | test | batch | itself, lines 1-20 | exact (extend existing) |
| `scripts/measure_db_growth.py` (new) | utility script | batch/read-only | `scripts/scrape_cooler_height.py` (argparse + `SessionLocal` + dry-run-by-default shape, minus the `--apply` since this is read-only) | role-match |
| `scripts/benchmark_provider.py` (new) | utility script | batch | `scripts/ask_free_ai.py` (sys.path/encoding setup, provider-chain usage, argparse CLI, no DB writes) | role-match |
| `tests/test_benchmark_provider.py` (new) | test | batch | `tests/test_price_freshness.py` (pure offline scoring, no DB/network) | role-match |

## Pattern Assignments

### `src/api/main.py` (config/middleware + controller, request-response)

**Analog:** `src/api/main.py` itself (current full file, 47 lines - read in full, see below)

**Current imports** (lines 1-7):
```python
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import builder, compare, images, products, stores
```
Add to this block: `from starlette.exceptions import HTTPException as StarletteHTTPException`,
`from fastapi.exception_handlers import http_exception_handler`, `from fastapi.responses import
JSONResponse, Response`, `from slowapi import Limiter`, `from slowapi.util import
get_remote_address`, `from configs import settings`.

**Current app construction** (lines 9-15) - change `docs_url`/`redoc_url` to be conditional and add
`openapi_url`, per RESEARCH.md Pattern 1:
```python
app = FastAPI(
    title="PC Builder API",
    description="REST API for PC component pricing, store comparisons, and historical price tracking.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
```

**Current CORS (the exact thing SEC-01 replaces)** (lines 17-24):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
Replace per RESEARCH.md's "CORS with an explicit allow-list" Code Example - keep the same
`app.add_middleware(CORSMiddleware, ...)` call shape, only change the argument values
(`allow_origins=settings.CORS_ALLOWED_ORIGINS`, `allow_credentials=False`,
`allow_methods=["GET", "POST"]`, `allow_headers=["Content-Type"]`).

**Existing static-file-serving pattern to copy for 404/500 branded pages** (lines 33-40):
```python
static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(static_dir / "index.html")
```
The new `branded_404`/`branded_500` handlers (RESEARCH.md Pattern 4) reuse `static_dir` and
`FileResponse(static_dir / "404.html", status_code=404)` exactly this way - no new response
style introduced.

**Router registration pattern to extend for `/robots.txt`, `/sitemap.xml`** (lines 26-31, 43-46):
```python
app.include_router(images.router, prefix="/api/v1")
...
@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "app": "PC Builder API"}
```
New `@app.get("/robots.txt", include_in_schema=False)` / `/sitemap.xml` routes follow this same
plain-function-decorated-route shape (see RESEARCH.md Code Examples).

---

### `src/configs/settings.py` (config, CRUD/env-read)

**Analog:** `src/configs/settings.py` itself (78 lines, read in full)

**Current env-var pattern** (lines 4-9, repeated throughout the file):
```python
import os
from dotenv import load_dotenv
load_dotenv()
...
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 20))
```

**The exact line SEC-02 must change** (lines 74-77):
```python
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://pc_builder:pc_builder123@localhost:5432/pc_builder"
)
```
Fix (per RESEARCH.md, "fail closed if unset"): `DATABASE_URL = os.environ["DATABASE_URL"]` (raises
`KeyError` if unset) or an explicit `if not DATABASE_URL: raise RuntimeError(...)` - either matches
the file's existing all-module-level-statements style (no class, no `pydantic.BaseSettings` used
anywhere in this file - do not introduce one).

**New `ENV` variable** - add alongside the other `os.getenv(...)` lines using the same style:
`ENV = os.getenv("ENV", "development")` (RESEARCH.md Pattern 1). Also add
`CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]`
in the same section style, for `main.py`'s new CORS middleware to import.

---

### `src/api/routes/builder.py` (controller/route, request-response - SEC-07)

**Analog:** `src/api/routes/builder.py` itself, `save_build` function (lines 232-275)

**Existing validation pattern to copy exactly** (lines 240-252, already-working unknown-ids check):
```python
selections = {slot: pid for slot, pid in (req.selections or {}).items() if pid}
if not selections:
    raise HTTPException(status_code=400, detail="Cannot save an empty build.")

unknown_slots = set(selections) - set(SLOT_CATEGORY)
if unknown_slots:
    raise HTTPException(status_code=400, detail=f"Unknown slots: {sorted(unknown_slots)}")

product_ids = list(selections.values())
found = {p.id for p in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
missing = set(product_ids) - found
if missing:
    raise HTTPException(status_code=400, detail=f"Unknown product ids: {sorted(missing)}")
```
Add `if len(selections) > 20: raise HTTPException(status_code=400, detail="Too many selections (max 20).")`
immediately after the empty-selections check, in the same `if ...: raise HTTPException(...)` style
(Pitfall 5 - implement even though not currently reachable).

**Body-size dependency** (new, per RESEARCH.md Code Examples "Body-size-capping dependency"):
```python
async def cap_body_size(request: Request, max_bytes: int = 10_000) -> None:
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail="Request body too large.")

@router.post("/builds", dependencies=[Depends(cap_body_size)])
def save_build(req: SaveBuildRequest, db: Session = Depends(get_db)):
    ...
```
This follows the file's existing `Depends(get_db)` dependency-injection convention (line 8, used at
line 233) - just add a second `Depends(...)` entry, no new pattern.

**Imports already present to reuse** (lines 1-16): `from fastapi import APIRouter, Depends,
HTTPException, Query` - add `Request` to this same import line.

---

### `src/api/routes/images.py` (route, file-I/O/streaming - SEC-04, test-only change)

**Analog:** `src/api/routes/images.py` itself (108 lines, read in full) - no source change required,
per RESEARCH.md the size/content-type check already works.

**The exact check already in place** (line 105):
```python
if r.status_code != 200 or not ctype.startswith("image/") or len(r.content) > MAX_BYTES:
    return _placeholder()
```
`MAX_BYTES = 5 * 1024 * 1024` is defined at line 31. New tests should call `product_image()`
directly (via `TestClient` against `app`, per the router's `@router.get("")` at line 85-86) or, more
simply following `tests/test_image_proxy.py`'s existing style, unit-test the pure helpers
(`is_allowed`, `_host`) plus one `httpx`-mocked integration test for the size/content-type gate.

**Existing test file to extend/mirror style from** (`tests/test_image_proxy.py`, full file, 40
lines) - plain `assert` functions, no fixtures, no DB, imports the module under test directly:
```python
from api.routes.images import _host, is_allowed

HOSTS = frozenset({"pcstudio.in", "mdcomputers.in"})

def test_store_image_allowed():
    assert is_allowed("https://www.pcstudio.in/wp-content/uploads/x.webp", HOSTS)
```
New size/content-type tests should mock `httpx.Client.get` (e.g. via `unittest.mock.patch` or
`respx`, whichever the project's `requirements.txt` already covers - `httpx>=0.28.0` is present) and
assert `product_image()` returns the SVG placeholder response, keeping the same no-fixture,
direct-import style.

---

### `.env.example` (config, file-I/O - SEC-08)

**Analog:** `src/configs/settings.py` (env-var names/defaults) + `docker-compose.yml` (env blocks,
lines 1-60 read)

**Full env-var inventory to cover** (from `settings.py`, all confirmed via full read):
`REQUEST_TIMEOUT`, `MAX_RETRIES`, `BACKOFF_FACTOR`, `LOG_LEVEL`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`,
`MISTRAL_API_KEY`, `GOOGLE_API_KEY`, `NVIDIA_API_KEY`, `FUZZY_MATCH_THRESHOLD`, `DATABASE_URL`
(11 vars per RESEARCH.md), plus the new `ENV` and `CORS_ALLOWED_ORIGINS`.

**From `docker-compose.yml`** (lines 1-53 read): `POSTGRES_PASSWORD`, `PGADMIN_DEFAULT_EMAIL`,
`PGADMIN_DEFAULT_PASSWORD`, `AIRFLOW_FERNET_KEY`, `AIRFLOW_WEBSERVER_SECRET_KEY`.

Format: one `KEY=` (or `KEY=<placeholder>`) line per var, comment above each explaining purpose,
matching the section-comment style already used in `settings.py` (`# --- ... ---` banners).

`tests/test_env_example.py` should parse both files (`.env.example` via a simple line-split on `=`,
`settings.py` via `re.findall(r'os\.getenv\("(\w+)"', ...)` or an AST walk) and assert every
`os.getenv`/`os.environ[...]` key in `settings.py` appears in `.env.example`, following
`tests/test_price_freshness.py`'s no-DB, pure-parsing test style.

---

### `src/services/compatibility_engine.py` (service, transform - FIT-01/02/03)

**Analog:** itself, full file already read (329 lines)

**The exact 3-line change point** (lines 221-223):
```python
def _eval_rule(self, rule, val_a, val_b) -> CompatibilityWarning | None:
    if val_a is None or val_b is None:
        return None  # not enough data to check yet - not an error, just unknown
```
Per RESEARCH.md Pattern 5 item 3, change the `None`-returning branch to distinguish exactly-one-side
missing (-> `unverified`, naming the part) from both-sides-missing (-> stays `None`, still
unchecked) and from Pitfall 8's derived-N/A fields (`aio_radiator_mm` on air coolers must NOT be
flagged unverified - check `compatibility_rules.py`'s per-rule comments, e.g. lines 55-56 and 60-62,
as the source of truth for which fields are legitimately N/A vs missing).

**Where to stamp `product_name`** - `_merge()` (lines 49-66) and each `_resolve_slot` branch
(lines 80-197) already loop `for p in products`; add `p.name` into each dict passed to `_merge`, or
set `ns.product_name = p.name` after each `_merge(...)` call in every one of the 8 category
branches (cpu/motherboard/ram/gpu/psu/case/cooler/storage) - each branch already has `p` in scope.

**The wattage code path to change separately (Pitfall 7 - FIT-03)** (lines 262-265, a *different*
block from `_eval_rule`, not covered by the above change):
```python
cpu_watt = sum((self._get(c, "tdp") or DEFAULT_CPU_TDP) for c in selections.get("cpu", []))
gpu_watt = sum((self._get(g, "tdp") or DEFAULT_GPU_TDP) for g in selections.get("gpu", []))
estimated_wattage = cpu_watt + gpu_watt + 50  # base system draw (board/RAM/storage/fans)
```
Add a `wattage_notes: list[str]` collected alongside this sum per RESEARCH.md Pattern 6, using the
now-available `product_name` field: `f"{self._get(c, 'product_name')}: no listed TDP, using typical
{DEFAULT_CPU_TDP}W"`.

**`validate_build`'s existing rule-loop structure to extend** (lines 249-260) - the new unverified
count/verdict computation slots into this same `for rule in RULES:` loop; no parallel iteration
system needed (Don't Hand-Roll table).

---

### `src/domain/builder.py` (model/Pydantic schema, transform - FIT-01/02/03)

**Analog:** itself (37 lines, read in full)

**Exact fields to extend** (lines 20-37):
```python
class CompatibilityWarning(BaseModel):
    level: str         # "error", "warning", "info"
    message: str

class BuildSummary(BaseModel):
    compatible: bool
    warnings: list[CompatibilityWarning]
    estimated_wattage: int
    total_min_cost: Decimal
    store_breakdown: list[StorePriceBreakdown]
```
`level`'s comment already anticipates a third value (currently unused per RESEARCH.md verification)
- add `"unverified"` as a valid value (no enum type exists in this file; it's a bare `str`, so no
`Literal`/enum migration is required, just documentation-comment update and usage elsewhere).
Add to `BuildSummary`: `unverified_count: int`, `verdict: str`, `wattage_notes: list[str] = []` -
same flat-field style as the existing four fields, no nesting.

---

### `src/static/app.js` (component, transform/render - FIT-01/02/03)

**Analog:** itself, lines 789-806 (verdict + warnings + wattage rendering block)

**Current 2-way verdict branch to change to 3-way** (lines 789-800):
```javascript
const statusEl = document.getElementById('compatibility-status');
const warningsEl = document.getElementById('warnings-list');
...
const wattageEl = document.getElementById('total-wattage');

if (summary.compatible) {
    statusEl.className = 'compatibility-status ok';
    ...
} else {
    statusEl.className = 'compatibility-status error';
    ...
}
```
Change to a 3-way branch reading `summary.verdict` (or re-deriving from `compatible` +
`unverified_count`, per Assumption A4) - same `getElementById` + `className`/`innerText` idiom, no
new rendering framework.

**Warnings-list rendering, needs NO structural change** (line 802):
```javascript
warningsEl.innerHTML = (summary.warnings || []).map(w => `
    <div class="warning-item ${w.level}">${w.message}</div>
`).join('');
```
A `level="unverified"` entry renders automatically through this existing `.map()`; web-dev only adds
a new CSS class `warning-item.unverified` in `style.css` (not in RESEARCH.md's scope list but
implied), no JS change needed here.

**Wattage line to extend for FIT-03** (line 806):
```javascript
wattageEl.innerText = `${summary.estimated_wattage || 0} W`;
```
Add a sibling element/line rendering `summary.wattage_notes` whenever non-empty, following the same
`document.getElementById(...).innerText = ...` idiom.

---

### `dags/scheduled_scraper_dag.py` (service/pure-function + orchestration wiring - OPS-05/06)

**Analog:** itself, lines 235-260 (`price_data_is_stale`, `check_price_freshness`) and 313-324 (task
wiring)

**Existing pure-function pattern (unchanged shape, extend the body)** (lines 238-240):
```python
def price_data_is_stale(latest: datetime | None, now: datetime, max_age: timedelta = PRICE_MAX_AGE) -> bool:
    """True when no price has been saved within max_age (or ever)."""
    return latest is None or now - latest > max_age
```
Keep this function exactly as-is (already per-store-agnostic, takes a single `latest` value) - only
`check_price_freshness()` (lines 243-260) changes to loop stores and call it once per store, per
RESEARCH.md Pattern 7's concrete rewrite:
```python
def check_price_freshness():
    with SessionLocal() as session:
        stores = session.scalars(select(Store).where(Store.active == True)).all()
        now_ = datetime.now()
        stale = []
        for store in stores:
            latest = session.scalar(
                select(func.max(PriceHistory.scraped_at))
                .join(Product, PriceHistory.product_id == Product.id)
                .where(Product.sid == store.id)
            )
            if price_data_is_stale(latest, now_):
                stale.append((store.display_name, latest))
    if stale:
        names = ", ".join(f"{n} (last: {t})" for n, t in stale)
        raise RuntimeError(f"No price saved in 24h for: {names}")
```

**The exception-swallowing pattern OPS-06 must NOT copy** (lines 115-119, `execute_canonical_extraction`):
```python
for label, fn in runners:
    try:
        fn(limit=limit_per_category)
    except Exception as e:
        print(f"[Canonical Extraction] {label} failed: {e}")
```
Do not thread return values through these 9 functions (Pitfall confirmed) - instead add a
`count_backlog(session)` pure function (RESEARCH.md Pattern 7) called before/after this stage.

**Task-wiring pattern to copy for the new `check_extraction_progress_task`** (lines 313-324):
```python
freshness_task = PythonOperator(
    task_id="check_price_freshness",
    python_callable=check_price_freshness,
    retries=0,
    trigger_rule="all_done",
    dag=dag,
)
...
process_targets_task >> freshness_task
```
New task follows the exact same `PythonOperator(..., trigger_rule="all_done", dag=dag)` shape,
wired as `canonical_extraction_task >> check_extraction_progress_task`.

**Import-guard pattern to preserve** (lines 264-266, 325-327) - all Airflow-specific code stays
inside the `try: from airflow import DAG ... except ImportError: pass` block; the new pure functions
(`count_backlog`, `check_extraction_progress`) must be defined OUTSIDE that guard (like
`price_data_is_stale`/`check_price_freshness` already are) so Phase 2's worker can import and call
them with no Airflow dependency.

---

### `tests/test_price_freshness.py` (test, batch - OPS-05/06)

**Analog:** itself, full file (20 lines, read in full)

```python
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dags"))
import scheduled_scraper_dag as dag  # noqa: E402

def test_recent_prices_are_fresh():
    now = datetime(2026, 9, 24, 12, 0)
    assert not dag.price_data_is_stale(now - timedelta(hours=2), now)
```
New per-store tests follow this exact `sys.path.insert` + module-level `import ... as dag` pattern
(no fixtures, no live DB - `price_data_is_stale` and the new `check_extraction_progress` are pure
functions, testable with plain `datetime`/`int` arguments).

---

### `scripts/measure_db_growth.py` (new utility script, batch/read-only - OPS-07)

**Analog:** `scripts/scrape_cooler_height.py` (argparse + `SessionLocal` + dry-run shape, minus the
`--apply` flag since this script writes nothing)

**Module docstring convention to copy** (lines 1-14 of `scrape_cooler_height.py`):
```python
"""
Fill air-cooler heights (cooler_specs.height_mm) from retailer product pages.
...
Dry-run by default. Pass --apply to write.
"""
import argparse
import sys
```
For `measure_db_growth.py`, the docstring instead states "Read-only. Never writes." (no `--apply`
flag needed at all, since OPS-07's script is inherently non-mutating).

**stdout-encoding guard to copy verbatim** (from `scripts/ask_free_ai.py`, lines 25-26):
```python
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

**`SessionLocal` usage pattern** (from `scrape_cooler_height.py` line 89, `db.session` import same
file):
```python
from db.session import SessionLocal
with SessionLocal() as session:
    ...
```

**argparse CLI convention** (from `scrape_cooler_height.py` lines 178-184):
```python
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--limit", type=int, default=None)
    ...
```
`measure_db_growth.py` should query `price_history` row count/date range and `products` row count
(mirroring the exact queries RESEARCH.md already ran this session: "database size 127 MB;
price_history 386,301 rows spanning 2026-07-27 to 2026-09-24"), printing plain `print(...)` output
in the same `"=" * 78` banner style used at `scrape_cooler_height.py` lines 96-99, 167-170.

---

### `scripts/benchmark_provider.py` (new utility script, batch - AI-01)

**Analog:** `scripts/ask_free_ai.py` (full file, 187 lines, read in full) for sys.path/encoding/CLI
conventions; `src/services/groq_extraction_service.py` for the provider/service interface to drive.

**Imports and encoding setup to copy verbatim** (`ask_free_ai.py` lines 19-30):
```python
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from services.groq_extraction_service import (  # noqa: E402
    GroqExtractionError, ProviderExhausted, default_service,
)
```

**Provider-chain interface to construct services against** (`groq_extraction_service.py` lines
112-113, 619-632, verbatim from RESEARCH.md Pattern 8):
```python
def provider_chain() -> list[tuple[str, str, str, str]]:
    """Providers to try in order, as (name, api_url, model, api_key), skipping any whose key is unset."""

_name, api_url, model, api_key = chain[0]
return GroqExtractionService(api_key=api_key, model=model, api_url=api_url, timeout=timeout)
```
`benchmark_provider.py` should accept `--provider {mistral,google,groq,cerebras}` (per Success
Criterion #5 naming "mistral and google") and construct `GroqExtractionService(api_key=..., model=...,
api_url=...)` directly for the chosen provider (from `provider_chain()`'s filtered entry), NOT
`default_service()` (which auto-picks the first available and would silently pick a different
provider than the one requested via CLI).

**Method to call** (`groq_extraction_service.py` line 519, signature only - body not needed here):
```python
def extract_batch(self, system_prompt: str, titles: list[str], max_retries: int = 4) -> list[dict]:
```
Call `service.extract_batch(PSU_IDENTITY_BATCH_PROMPT, titles)` with the bare prompt constant
(imported directly, `from services.groq_extraction_service import PSU_IDENTITY_BATCH_PROMPT`), per
RESEARCH.md's explicit warning not to use `identity_prompt('psu')` (that variant appends live DB
brand hints, breaking reproducibility and adding an unwanted DB read).

**CLI argparse convention to copy** (`ask_free_ai.py` lines 143-150):
```python
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("prompt", nargs="?", default="-", ...)
    ap.add_argument("--json", action="store_true", ...)
    args = ap.parse_args(argv)
    ...

if __name__ == "__main__":
    sys.exit(main())
```
`benchmark_provider.py`'s CLI: `--provider <name>` (required), no `--apply`/write flag at all (AI-01
requires zero DB writes - this script must not import `db.session.SessionLocal` anywhere, unlike
`scrape_cooler_height.py`/`measure_db_growth.py`). Score against the answer-key table in
RESEARCH.md's "Reconstructing the AI-01 benchmark" section (8 product titles + independently
verified `efficiency_rating` answers - re-confirm each against `data/raw/All_certified_psus.xlsx`
before locking them in, per Pitfall 9).

**Error handling to copy** (`ask_free_ai.py` lines 170-174, `GroqExtractionError` catch -> exit code
1, `ProviderExhausted` sub-fallback loop lines 118-138) - reuse the same
`except GroqExtractionError as e: print(..., file=sys.stderr); return 1` shape; benchmark scoring
should not "chain fallback" across providers (that's `ask_free_ai.py`'s
job for interactive use) - a benchmark run must fail loudly for the *specific* provider under test,
not silently substitute another one.

---

### `tests/test_benchmark_provider.py` (new test, batch - AI-01)

**Analog:** `tests/test_price_freshness.py` (pure offline function test, no DB/network dependency,
same file read above)

Test the **scoring function** only (compare parsed `efficiency_rating` per title against the answer
key dict), with the 8 titles/answers hardcoded as test fixtures - no live HTTP call in this test
(the manual `python scripts/benchmark_provider.py --provider mistral` run against a real provider is
a separate, non-pytest validation step per RESEARCH.md's Sampling Rate section).

---

### `src/static/404.html`, `500.html`, `about.html`, `privacy.html` (new static components - WEB-01/02/05)

**Analog:** `src/static/index.html` (head block lines 1-8, footer lines 172-183, read above)

**Head structure to copy** (lines 1-8):
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PC Builder 2 - Hardware Price Comparison & Assembly Engine</title>
    <link rel="stylesheet" href="/static/style.css?v=8">
</head>
```
404/500/about/privacy pages should reuse this exact `<head>` shape (same stylesheet link, same
viewport meta) with page-specific `<title>`, so they visually match the rest of the site rather than
introducing a second design system. `index.html`'s own `<head>` also gains the new SEO meta/OG/
canonical/favicon tags per SEO-01 - add these lines to the existing 8-line block, not a rewrite.

**Footer link target for About/Privacy** (lines 172-183, read above) - `about.html`/`privacy.html`
are linked from this existing `<footer class="site-footer">` block; WEB-05 needs `<a href="/static/
about.html">` (or a mounted route) added inside `.footer-note` or as a new `<nav>` inside the footer,
not a new footer element type.

---

### `tests/test_frontend_e2e.py` (extend existing - WEB-03/04/05)

**Analog:** itself, lines 1-80 (fixtures, read in full above)

**Fixtures to reuse unchanged:**
```python
@pytest.fixture(scope="module")
def base_url():
    """Boot the real app on a scratch port, so tests never touch the dev server."""
    ...

@pytest.fixture(scope="module")
def browser():
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            yield b
            b.close()
    except Exception as exc:
        pytest.skip(f"chromium unavailable: {exc}")

@pytest.fixture
def page(browser, base_url):
    pg = browser.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(base_url, wait_until="networkidle")
    pg.console_errors = errors
    yield pg
    pg.close()
```
The new 375px viewport test (WEB-04) adds a **new fixture** `mobile_page` following the exact same
shape as `page`, but calling `browser.new_page(viewport={"width": 375, "height": 812})` before
`.goto(...)` - do not modify the existing `page` fixture (other tests depend on its default
viewport). Selectors to reuse, per RESEARCH.md: `#search-input`, `#slots-container`,
`#select-modal`, `#compatibility-status` (all verified to exist in `index.html`/this test file
already).

---

## Shared Patterns

### Dependency injection via `Depends(get_db)`
**Source:** `src/api/deps.py` (full file, 14 lines, read above):
```python
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```
**Apply to:** any new route needing a DB session (none of Phase 1's new routes need one beyond what
`builder.py`/`images.py` already have) and as the model for the new `cap_body_size` dependency in
`builder.py` (same `Depends(...)` composition style, chained via `dependencies=[Depends(...)]`).

### Static-file serving via `FileResponse`
**Source:** `src/api/main.py` lines 34-40 (`static_dir`, `serve_index()`)
**Apply to:** `404.html`/`500.html` branded-error handlers (`src/api/main.py`), and any future
`about.html`/`privacy.html` explicit routes if not served purely via the existing `/static` mount.

### Dry-run-by-default CLI scripts
**Source:** `scripts/scrape_cooler_height.py` lines 13, 178-184 (`--apply` flag, dry-run default) and
`scripts/ask_free_ai.py` lines 19-30 (encoding guard, argparse, exit codes)
**Apply to:** `scripts/measure_db_growth.py` (read-only, no `--apply` needed - never writes at all)
and `scripts/benchmark_provider.py` (no `--apply` either - AI-01 explicitly forbids DB writes; the
"dry-run" framing here means "never touches the DB", not "requires a flag to write").

### Pure functions callable by both Airflow and a future plain worker
**Source:** `dags/scheduled_scraper_dag.py` lines 235-260 (`price_data_is_stale`,
`check_price_freshness` defined OUTSIDE the `try: from airflow import DAG` guard at lines 264-327)
**Apply to:** the new `count_backlog()`/`check_extraction_progress()` functions (OPS-06) - must be
defined at module level, outside the Airflow import-guard block, exactly like the existing freshness
functions, so Phase 2's worker (per ROADMAP.md 02-03) can `from scheduled_scraper_dag import
check_extraction_progress` with no Airflow installed.

### Provider-chain-aware LLM service construction
**Source:** `src/services/groq_extraction_service.py` lines 112-113 (`provider_chain()`), 619-632
(`default_service()`), 426-444 (`GroqExtractionService.__init__`, `_fallbacks` list)
**Apply to:** `scripts/benchmark_provider.py` must construct a `GroqExtractionService` bound to one
specific provider from the chain (not `default_service()`'s auto-pick), per the file-specific
pattern assignment above.

### No-DB, no-fixture pure-function unit tests
**Source:** `tests/test_image_proxy.py` (full file), `tests/test_price_freshness.py` (full file),
`tests/test_compatibility_rules.py` (lines 1-22)
**Apply to:** `tests/test_settings.py`, `tests/test_env_example.py`, `tests/test_benchmark_provider.py`
(offline scoring), and the pure-function half of `tests/test_price_freshness.py`'s extension - all
follow "import the module/function directly, assert on plain values, no `TestClient`, no live DB".

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/test_docs_disabled.py` | test | request-response | No existing test toggles an env var and re-imports `api.main` to assert route registration changed; nearest is `tests/test_price_freshness.py`'s env-var-adjacent style (uses fixed datetimes, not env vars) - use RESEARCH.md's Pattern 1 code example plus `monkeypatch.setenv("ENV", "production")` + re-import `api.main` as the shape for this file. |
| `tests/test_seo_basics.py` | test | request-response | No existing test fetches `/`, `/robots.txt`, `/sitemap.xml` and asserts on HTML head content; nearest structural relative is `tests/test_error_pages.py` (also new, needs a live app via `TestClient(app)` or the `base_url` subprocess fixture) - RESEARCH.md's Code Examples section gives the exact `robots.txt`/`sitemap.xml` route bodies to test against. |

## Metadata

**Analog search scope:** `src/api/`, `src/services/`, `src/domain/`, `src/configs/`, `src/static/`,
`dags/`, `scripts/`, `tests/` (all directories named in RESEARCH.md's Recommended Project Structure
and ROADMAP.md Phase 1 file lists)
**Files scanned:** 19 existing files read directly (all confirmed git-tracked via `git ls-files`),
plus RESEARCH.md's own verbatim-quoted line ranges cross-checked against the live files
**Pattern extraction date:** 2026-09-24
