---
last_mapped_commit: a803b6fdb669c9fb39477658b3e08c0a134f8cf2
last_mapped_at: 2026-09-24
---
# Codebase Concerns

**Analysis Date:** 2026-09-24

## Critical Issues Blocking Public Launch

### Frontend Console Errors (Open)

**Failing Test:**
- Location: `tests/test_frontend_e2e.py::TestPageLoads::test_no_console_errors_on_load`
- Error: 3 `ERR_BLOCKED_BY_RESPONSE.NotSameOrigin` console errors on page load
- Files affected: `src/static/app.js`, cross-origin resources (likely store-hosted images)
- Symptom: Browser console shows CORS/cross-origin policy rejections
- Impact: Not a data or logic failure, but signals security policy or image proxy misconfiguration
- Status: Documented in PROGRESS.md as open, not user-visible but fails CI/CD

**Do this instead:** Verify image proxy (`src/api/routes/images.py`) is correctly intercepting cross-origin image requests before they reach the browser. Ensure all store images are being proxied through `GET /api/v1/images?u=`.

### Missing Environment Variable Documentation

**Problem:** No `.env.example` file exists; new deployments have no reference for required configuration.

**Files:** 
- `src/configs/settings.py` (lines 58-77) reads: `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `MISTRAL_API_KEY`, `GOOGLE_API_KEY`, `NVIDIA_API_KEY`, `DATABASE_URL`, `REQUEST_TIMEOUT`, `MAX_RETRIES`, `BACKOFF_FACTOR`, `LOG_LEVEL`, `FUZZY_MATCH_THRESHOLD`, and Airflow/Postgres variables in `docker-compose.yml`.
- `.env` file (git-ignored, not tracked)

**Impact:** Fresh clone cannot run; developer must guess which env vars are required. CI/CD, containerized deployments, and team onboarding all blocked.

**Fix approach:** Create `.env.example` with all required variables and non-secret defaults. Document in README.md the deployment checklist.

### Hardcoded Default Database URL

**Problem:** `src/configs/settings.py:76` contains hardcoded credentials:

```python
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://pc_builder:pc_builder123@localhost:5432/pc_builder"
)
```

**Risk:** 
- Credentials embedded in source code (even as fallback)
- Insecure default password (`pc_builder123`)
- Production deployments may accidentally use this if `DATABASE_URL` env var is not set

**Fix approach:** Remove default entirely, or use a placeholder that raises an error if not overridden:

```python
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")
```

### CORS Allows All Origins with Credentials

**Problem:** `src/api/main.py:18-24`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Risk:** Allows any website to make authenticated requests to the API on behalf of a user's browser session. `allow_credentials=True` + `allow_origins=["*"]` violates CORS security principles.

**Impact:** 
- Enables cross-site request forgery (CSRF) attacks
- Session hijacking if cookies/tokens are ever added
- API is publicly accessible without domain restriction

**Fix approach:** 
- Restrict `allow_origins` to known frontend domains (or skip if single-domain app)
- If cross-origin requests are needed, use `allow_credentials=False` and rely on CORS preflight
- Add CSRF tokens to state-changing requests (POST/PUT/DELETE)

## Data Quality & Reliability Issues

### Scraping Pipeline Silently Stopped for 38 Days

**Problem:** No price updates saved between 2026-08-17 and 2026-09-24 (38 days).

**Root causes (2026-09-24 PROGRESS.md):**
1. Airflow container was down entirely from 2026-08-18 to 2026-09-20
2. `ProductRepository.create()` was called with `condition` parameter but the method signature didn't accept it (287e304 added to `SearchService.save()` but forgot `.create()`)
3. Every scrape batch rolled back silently; status still marked **success**

**Files:** 
- `dags/scheduled_scraper_dag.py:execute_due_scrape_targets()` (lines 71-80) catches per-target exceptions but had no detection if every target failed
- `src/services/search_service.py` (method signature mismatch)

**Current Guard:** Added two checks (PROGRESS.md 2026-09-24):
- Scrape task now fails if every target fails
- Separate `check_price_freshness` task fails if no price saved in 24h
- Both in `dags/scheduled_scraper_dag.py`

**Risk:** Even with guards, a single silent scraper error can go unnoticed for a full cycle. Monitoring is reactive, not proactive.

**Fix approach:** 
- Add logging with `DEBUG` level showing which targets succeeded/failed
- Alert/notify if any price freshness check fails
- Consider a weekly "sanity check" DAG task that verifies products from each store were touched

### LLM Provider Quota Exhaustion & Fallback Chain Fragility

**Current state (PROGRESS.md 2026-09-20):**

| Provider | Status | Notes |
|----------|--------|-------|
| **groq** | ✅ Primary (openai/gpt-oss-120b) | ~15s throttle on free tier, honors retry-after |
| **google** | ✅ Fallback (gemini-3.1-flash-lite) | Via OpenAI-compatible endpoint |
| **mistral** | ⚠️ Quota exhausted | A one-token probe 429s |
| **cerebras** | ❌ 402 Payment Required | Account authentication issue |
| **nvidia** | ❌ 500/410 errors | Chat completions failing |

**Risk:** Only 2 working providers. If Groq is throttled/down, Google fallback is the only option. If both fail, all LLM extraction stalls.

**Impact:** Canonical identity extraction stops working → spec matching breaks → builder compatibility engine degraded.

**Files:** 
- `src/services/groq_extraction_service.py` (provider chain logic)
- 15 extraction scripts in `scripts/extract_*_titles_groq.py` and `scripts/extract_*_specs_groq.py`

**Local Inference Untested:** PROGRESS.md 2026-09-20 notes local inference on Ollama/AMD GPU untested on Windows ROCm path.

**Fix approach:** 
- Add monitoring of provider health (test quota before running extraction)
- Implement exponential backoff + circuit breaker for exhausted providers
- Document fallback sequence and manual override if needed
- Test local inference path before relying on it

### TLG Gaming Prices Still Partially Broken

**Problem:** TLG Gaming (`sid=11`) had systematically broken prices. Partially fixed 2026-08-17:

**Original issue (2026-08-17):**
- `Rs.` prefix instead of `₹` not handled
- Selector too broad (`.price` container holding both price and tax)
- Result: 0-priced products; catalog-wide unpriced: 163 → 0

**Current issue (PROGRESS.md 2026-08-17):**
- Parser was completely rewritten and fixed (2026-08-17)
- All 163 products now re-scraped with correct prices
- Status: Fixed

**Fragility:** The parser for `.price-new, .price-normal` works, but if TLG Gaming changes their HTML structure (which online retailers do frequently), the scraper fails silently.

**Files:** `src/scrapers/` (TLG Gaming-specific parsing)

**Fix approach:** Add per-scraper tests (sample 10-20 products from each store daily) to catch structural changes early.

### Missing Product Images

**Current state:** 116 of 11,824 products missing images (PROGRESS.md 2026-08-17). All out of stock, so not blocking purchases, but affects browsing experience.

**Cause:** Store hotlinks blocked by cross-origin policies or dead links.

**Current mitigation:** `GET /api/v1/images?u=` proxy with "No image" SVG placeholder.

**Remaining gap:** User sees placeholder; no indication of whether it's a dead link or unavailable image.

**Fix approach:** Add image proxy stats/health check; consider bulk re-scraping image URLs from product pages.

## Fragile Architecture Areas

### Canonical ID Collisions & Data Merges

**History of false merges (PROGRESS.md 2026-09-24):**

1. **Cabinet colour field collapsed 34+15 models into one fake group** (2026-09-24)
   - Solution: Add `color`/`colour` to `_NON_IDENTIFYING_FIELDS`
   - Re-extraction re-keyed without issues

2. **Brand-only groups merged 26 different products** (2026-09-24)
   - `case:silverstone` held 3 different rackmount chassis
   - Solution: Add `brand`/`aib_brand` to `_NON_IDENTIFYING_FIELDS`
   - 34 listings released, 0 conflicts after re-extraction

3. **PSU efficiency trim caused silent merges** (PROGRESS.md 2026-09-20)
   - First dry-run split 47 groups, almost all incorrectly
   - Solution: Reconciliation logic in `matching/psu_identity.py` + add trim to key

4. **Motherboard ITX/microATX merge** (PROGRESS.md, resolved)
   - B850/B850I collapsed into one canonical group
   - Solution: Include form_factor in key

**Pattern:** Every non-identifying qualifier field risks collapsing different products into one. Adding fields to `_NON_IDENTIFYING_FIELDS` is reactive, not proactive.

**Files:** 
- `src/matching/canonical_key_builder.py` (key assembly)
- `src/matching/_non_identifying_fields` (field safelist)
- `scripts/fix_canonical_collisions.py` (cleanup, last-resort)

**Fragility:** Test for this bug class checks for near-duplicate *splits*, missing over-merges entirely (PROGRESS.md 2026-09-24: "a false **merge** is invisible to a split-detector").

**Fix approach:** 
- Add unit tests for group-to-listing ratio (detects over-merges)
- Run both split and merge audits in CI
- Any new spec/extraction field must have a test asserting it doesn't merge different models

### Session Management Has No Error Handling

**Problem:** `src/api/deps.py:get_db()` has no handling for database connection failures.

```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # No cleanup if yield fails, DB pool exhausted on error
```

**Risk:** 
- If `SessionLocal()` fails (DB down, pool exhausted), the exception propagates without resource cleanup
- Connections may leak if an exception occurs during `yield`
- FastAPI returns 500 error with no context

**Impact:** API becomes unresponsive if database connection pool is exhausted or DB is down.

**Fix approach:** 

```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

### Image Proxy Timeout & Redirect Limits Are Hardcoded

**Problem:** `src/api/routes/images.py:85-107`

```python
with httpx.Client(timeout=8.0, follow_redirects=False, headers=HEADERS) as client:
    # ...
    for _ in range(3):  # Hardcoded limit!
        if not r.is_redirect:
            break
        # ...
```

**Risk:** 
- 8-second timeout insufficient for slow CDNs (Shopify, Bunny CDN under load)
- 3-hop redirect limit is arbitrary; some stores may use more
- No per-hop timeout (if one redirect takes 8s, next one has 0s left)

**Impact:** Image requests timeout → placeholders shown unnecessarily.

**Fix approach:** 
- Make timeout configurable via env var (e.g., `IMAGE_FETCH_TIMEOUT_S`)
- Increase default to 15-20s for CDNs
- Track redirect chains and log excessive redirects as warnings

### Empty Exceptions Module

**Problem:** `src/common/exceptions.py` is empty.

**Impact:** 
- No custom exception hierarchy
- Error handling is `raise RuntimeError()` or `HTTPException()`
- Harder to catch/log specific error types

**Fix approach:** Define domain exceptions:

```python
class ScraperError(Exception): pass
class ExtractionError(Exception): pass
class CompatibilityCheckError(Exception): pass
```

### DAG Error Handling Is All-or-Nothing

**Problem:** `dags/scheduled_scraper_dag.py:execute_due_scrape_targets()` (lines 71-80)

```python
if attempted and failed == attempted:
    raise RuntimeError(f"All {attempted} scrape targets failed")
```

**Risk:** 
- One bad target causes entire stage failure (but was working before 2026-09-24 guard)
- `trigger_rule="all_done"` downstream means extraction still runs even if scrape fails
- No per-target retry logic (Tenacity lib exists but not used in DAG)

**Impact:** If 9/10 stores scrape successfully, 1 store's data is stale for a full cycle. Downstream tasks run regardless.

**Fix approach:** 
- Add per-target retry with exponential backoff
- Log which targets failed, separate from task failure
- Consider downstream task dependency: if scrape fails, skip extraction for that target

## Performance & Scalability Concerns

### Airflow LocalExecutor Not Scaling

**Problem:** `docker-compose.yml:40` + `docker-compose.yml:47`

```yaml
environment:
  - AIRFLOW__CORE__EXECUTOR=LocalExecutor

```

**Impact:** All DAG tasks run sequentially in a single process. Scraping 10 stores waits for each to finish (6-8s per store × 10 = 60-80s), even though they're independent.

**Fix approach:** Switch to `CeleryExecutor` (requires Redis) or `KubernetesExecutor` for production. Document in deployment guide.

### Image Proxy Host Cache Has Fixed TTL

**Problem:** `src/api/routes/images.py:32-33`

```python
HOSTS_TTL_S = 600  # Hardcoded 10 minutes
_hosts_cache: tuple[float, frozenset[str]] = (0.0, frozenset())
```

**Risk:** 
- If a store adds a new domain, it won't be recognized until cache expires
- Stale data silently returned for 10 minutes
- No way to invalidate cache on demand

**Fix approach:** 
- Make TTL configurable (env var: `IMAGE_HOSTS_CACHE_TTL_S`)
- Add cache invalidation endpoint (admin-only) or `/health/cache` to verify freshness
- Log cache hits/misses

### No Database Indexes for Canonical ID Lookups

**Problem:** Specs tables are keyed by `canonical_id`, but indexes are not mentioned in migrations.

**Files:** `src/db/migrations/versions/` (9 spec table migrations)

**Risk:** `CompatibilityEngine._resolve_slot()` joins on `canonical_id` frequently. Without an index, queries degrade as catalog grows.

**Fix approach:** 
- Run `EXPLAIN ANALYZE` on key queries to identify missing indexes
- Add indexes on `*_specs.canonical_id` and `products.canonical_id` if not present
- Document index strategy in deployment guide

## Security Concerns

### No Authentication/Authorization

**Problem:** All API endpoints are public. No session, token, or API key auth.

**Risk:** 
- Anyone can call `/api/v1/builder/validate`, `/api/v1/products`, etc.
- No rate limiting → DOS attack vector
- Saved builds are "protected" only by unguessable share tokens (works, but fragile)

**Files:** `src/api/routes/` (all routes lack auth)

**Fix approach:** 
- If frontend-only (internal tool), add IP whitelist at proxy/firewall
- If public API, implement token-based auth (JWT or API keys) + rate limiting
- Document API terms of service (scraping restriction?)

### No Rate Limiting

**Problem:** No `SlowAPI` or similar rate limiting middleware.

**Risk:** 
- Bulk requests from external tool can overload API
- Image proxy can be used to make server request arbitrary (permitted) hosts
- Extraction jobs compete for CPU with API requests

**Fix approach:** Add `SlowAPI` middleware:

```python
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@router.get("")
@limiter.limit("10/minute")
def list_products(...): pass
```

### Image Proxy Host Validation Is Not Airtight

**Problem:** `src/api/routes/images.py:70-77`

```python
def is_allowed(url: str, hosts: frozenset[str]) -> bool:
    h = _host(url)
    if h in IMAGE_CDN_HOSTS:
        return True
    return any(h == allowed or h.endswith("." + allowed) for allowed in hosts)
```

**Risk:** 
- Subdomain matching allows `h.endswith(".example.com")` → `attacker.example.com` would bypass if `example.com` is in hosts
- No path validation; a redirect to `store.example.com/../../sensitive` might slip through

**Mitigation:** Already in place: only `http`/`https` schemes allowed, redirects checked per-hop.

**Fix approach:** 
- Use `urllib.parse.urlsplit` to separate host/path for cleaner logic
- Add path constraints if needed (allow `/cdn/` only?)
- Log all blocked/suspicious requests

### Cross-Origin Resource Policy Blocking User Images

**Problem:** PCStudio sends `Cross-Origin-Resource-Policy: same-origin` on images.

**Impact:** Browser blocks images from being loaded cross-origin. Image proxy (`GET /api/v1/images`) mitigates, but console errors persist.

**Files:** `src/api/routes/images.py` (mitigation), `src/static/app.js` (image loading)

**Current workaround:** Proxy intercepts; app.js uses `<img src="/api/v1/images?u=...">` instead of direct hotlink.

**Remaining issue:** Test `test_no_console_errors_on_load` still fails with ERR_BLOCKED_BY_RESPONSE, indicating some images bypass proxy or policy still blocks.

**Fix approach:** Audit `src/static/app.js` to ensure all image loads go through proxy.

## Test Coverage Gaps

### Frontend E2E Tests Require Playwright

**Problem:** `tests/test_frontend_e2e.py:24` imports Playwright and skips if not installed.

```python
playwright_api = pytest.importorskip("playwright.sync_api")
```

**Risk:** 
- CI/CD may not have browser binary installed → tests skipped silently
- Regressions in HTML/CSS/JS not caught if browser env missing
- Locally tests pass, CI silently skips them

**Fix approach:** 
- Add Playwright to CI dependency matrix (install browser binary in CI)
- Fail CI if tests are skipped due to missing browser (assert they ran)
- Document browser setup in README

### No Integration Tests for Full Pipeline

**Problem:** Tests exist for scrapers, extractors, builder logic separately, but no end-to-end test that verifies: scrape → extract → compatibility engine → API response.

**Risk:** 
- A scraper/extractor change may break the end-to-end flow without failing unit tests
- Example from PROGRESS.md: builder validation broke because `app.js` posted wrong field name; backend test passed

**Fix approach:** Add integration test in `tests/` that:
1. Mocks a scraper result
2. Runs extraction on it
3. Calls `/api/v1/builder/validate` with the result
4. Asserts compatibility check passes/fails as expected

### No Tests for Data Migrations

**Problem:** Alembic migrations in `src/db/migrations/versions/` are not tested.

**Risk:** 
- A migration may fail on production data (e.g., constraint violation)
- Rollback is untested; a migration can't be undone if it corrupts state
- Adding a column with a non-null default on existing rows can lock the table

**Fix approach:** 
- Add `tests/test_migrations.py` with sample data before/after each migration
- Test both upgrade and downgrade paths
- Document migration risks (table locks, foreign key checks) in migration docstrings

## Data Integrity Issues

### Spec Data Sourced from Multiple Methods with Different Reliability

**Current sourcing (PROGRESS.md 2026-08-16):**

| Category | Coverage | Primary Source | Confidence |
|----------|----------|-----------------|------------|
| CPU specs | 136 models | Mistral + Claude cross-verify + web search | High (50), Medium (78), Low (8) |
| Monitor specs | 826 models | Mistral grounded extraction | 705 high-confidence |
| GPU specs | 555 models | **Bulk import from RightNow-GPU-Database** | 506 high-confidence |
| PSU specs | 446 models | Cybenetics lab certs + Mistral | 332 high-confidence |
| RAM specs | 834 models | **Derived from title extraction** (zero API calls) | 716 high-confidence |
| SSD specs | 805 models | **Derived from title extraction** (zero API calls) | 730 high-confidence |
| Motherboard specs | 1,359 models | Mistral grounded extraction | Only 40 high-confidence |
| Cooler specs | 585 models | Mistral grounded extraction | Only 34 high-confidence |
| Cabinet specs | 1,405 models | Web scrape + Mistral | Only 10 high-confidence |

**Fragility:** Motherboard, cooler, cabinet specs have very low high-confidence coverage (2-3%). A bulk dataset or web scrape could improve this, but maintainability is low.

**Fix approach:** 
- Document per-category sourcing strategy (which is authoritative?)
- For motherboard: consider importing from Gigabyte/ASUS/MSI/ASRock spec sheets
- For cooler: leverage TDP/socket data from product pages
- For cabinet: retailer product pages often have full spec tables

### Cabinet Clearance Coverage Still Incomplete

**Current state (PROGRESS.md 2026-09-24):**
- GPU clearance: 820 of 1,404 live cabinet models (65% coverage)
- Cooler height: 732 models
- Radiator sizes: 1,017 of 1,459 models (70% coverage)

**Gaps:** 35-40% of cabinets have no clearance data. Compatibility engine leaves these as warnings, not errors, which is safe but incomplete.

**Root cause:** Retailer pages don't state clearances for many models (especially budget cases). LLM cannot estimate.

**Impact:** Users may miss warnings for incompatible builds (e.g., RTX 5090 in a tight case).

**Fix approach:** 
- Maintain a manual registry of common case dimensions from manufacturer specs
- Integrate with TechSpot case reviews (GPU clearance, radiator support often documented)
- Mark cases as "clearance unknown" prominently in UI (not a silent gap)

### Missing Error Pages

**Problem:** No custom error pages (404, 500, 403) defined.

**Files:** `src/api/main.py` (app initialization), `src/static/` (no error HTML)

**Risk:** 
- Users see default FastAPI error pages (revealing framework/version info)
- No branding; looks unfinished
- 404s should guide users back (e.g., "Component not found. Try searching?")

**Fix approach:** Define error handlers in `src/api/main.py`:

```python
@app.exception_handler(404)
async def not_found(request, exc):
    return FileResponse(static_dir / "404.html")
```

Create `src/static/404.html`, `500.html`, etc.

## Known Bugs & Workarounds

### Cooler Socket Lists Inconsistently Normalized

**State (PROGRESS.md, open):** 21/585 coolers have socket data. 4 use bare forms like `"115x,1200"` that won't string-match `"LGA1151"`, causing false warnings.

**Impact:** Low (rule is warning-level, not blocking). Affects maybe 4 builds out of 11,824 products.

**Fix approach:** Normalize socket lists on read:

```python
sockets = re.sub(r'115x', 'LGA115x', cooler.sockets)  # etc.
```

### PCStudio Had Truncated Product Names (Fixed)

**State (PROGRESS.md 2026-08-17):** Fixed. 1,793 products truncated, now 59 remaining out of stock.

**How it broke things:** 
- Canonical keys built from truncated title → mismatches
- Spec extraction read incomplete text (e.g., "CL3" instead of "CL30")
- Search couldn't match past cut-off text

**Lesson:** Retailers change HTML structure frequently. Need per-store regression tests.

### TLG Gaming Parser Still Fragile

**State (PROGRESS.md 2026-08-17):** Fixed but fragile. Changed from `Rs.` + loose regex to `Rs.` prefix + selector refinement.

**Risk:** If TLG Gaming changes their HTML class names or structure, silent price failure again.

**Fix approach:** Add smoke test to daily health check: fetch 5 random TLG Gaming products, verify price > 100.

### PSU Efficiency Confusion (Cybenetics vs 80 PLUS)

**State (PROGRESS.md 2026-09-20):** Fixed. All 452 `psu_specs` rows are now `status='ok'` with correct 80 PLUS tier.

**History:** Titles carry both Cybenetics (Platinum, Gold, Silver) and 80 PLUS (Gold, Silver, Bronze) ratings. Models were reading "Platinum" from Cybenetics, wrong tier for 80 PLUS.

**Solution:** Prompt now specifies: report 80 PLUS only, ignore Cybenetics.

**Remaining known conflicts:** 2 MSI units where model name says "GL" (Gold) but key says different tier. Left for manual review.

---

## Deployment Readiness Gaps

### No `.env.example` for New Deployments

**Impact:** Fresh clone requires guessing which environment variables are needed. Blocks CI/CD setup.

### No Deployment Documentation

**Risk:** No runbook for moving to production. Questions unanswered:
- How to back up PostgreSQL?
- How to scale Airflow (currently LocalExecutor)?
- How to enable HTTPS?
- How to set up monitoring?

### No Health Check for Data Freshness Beyond Price Check

**Current:** Only `check_price_freshness` task (DAG level).

**Missing:** 
- Are scraper endpoints still reachable?
- Is LLM extraction working?
- Are database connections healthy?

### Hardcoded Configuration Values

**Issues:**
- Airflow container port: `8085` (hardcoded in docker-compose.yml)
- FastAPI port: `8000` (not in docker-compose, must be set at runtime)
- Static file paths: assumed to exist at `src/static/`
- Image cache TTL: `600` seconds

**Fix approach:** Move all to env vars with defaults documented.

### No Graceful Shutdown for Long-Running Tasks

**Problem:** DAG tasks (scraping, extraction) don't handle SIGTERM gracefully.

**Risk:** Scaling down pods mid-scrape leaves partial data.

**Fix approach:** Add signal handlers to tasks, checkpoint progress to DB before shutdown.

---

## Summary: What Blocks Public Launch

1. ✅ **Fix console errors test** — 3 cross-origin errors, image proxy incomplete
2. ❌ **Add `.env.example`** — Deployment impossible without it
3. ❌ **Remove hardcoded DB credentials** — Security risk and bad config practice
4. ⚠️ **Fix CORS** — Allow-all-origins with credentials violates security
5. ❌ **Add rate limiting** — DOS attack vector exposed
6. ❌ **Add error pages** — 404/500 return framework internals
7. ❌ **Add deployment docs** — No runbook for production
8. ⚠️ **Test image proxy thoroughly** — Ensure all hotlinks are intercepted
9. ⚠️ **Monitor data freshness** — Scraping can silently stop again
10. ⚠️ **Add fallback for LLM providers** — Only 2 working; system fragile if one down

---

*Concerns audit: 2026-09-24*
