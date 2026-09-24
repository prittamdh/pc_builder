# Phase 1: Launch hardening - Research

**Researched:** 2026-09-24
**Domain:** FastAPI security hardening, honest compatibility-verdict semantics, per-store data-freshness checks, LLM provider benchmarking
**Confidence:** HIGH

## Summary

This phase touches four independent problem areas, and for thirteen of the twenty requirements the
current code was read directly this session (not inferred from the codebase-map docs, which this
research corrects in three places - see Assumptions/pitfalls below). The picture is more nuanced
than "everything is broken": a few of the scariest-sounding requirements (WEB-01's JSON 404 for
`/api/*`, most of WEB-02's no-traceback guarantee) are **already satisfied by FastAPI/Starlette's
defaults** and only need a test written. Others (SEC-01 CORS, SEC-02 default DB credential, SEC-06
docs-in-prod, FIT-01/02/03) are genuinely unimplemented and confirmed so by reading the exact lines.

The single most important design decision in this phase is **FIT-01/02/03**: the compatibility
engine's `_eval_rule` (`src/services/compatibility_engine.py:221-223`) returns `None` - not a
warning - whenever either side of a rule is missing data, which is indistinguishable from "checked,
no problem" both in the API response and in `app.js`. The fix is not a new subsystem: it is a third
value for `CompatibilityWarning.level` (today only `"error"`/`"warning"`, with `"info"` reserved but
unused) plus a `product_name` carried on the merged spec views so the new "unverified" message can
name the part. This reuses 100% of the existing rule-iteration and rendering machinery.

The second load-bearing finding is that **AI-01's "the 8 titles and answers from the 2026-09-20 run"
were never committed anywhere** - not as a script, not as a data file, not as a git-history diff
across any branch. Only the aggregate scores ("8/8") survive, in `PROGRESS.md` prose and a test
docstring. This phase's data-engineer plan must **reconstruct**, not "recover," the benchmark. This
research identifies real, currently-catalogued product titles (verified against the live database
this session) that reproduce the documented trap cases exactly, including the literal title quoted
in `PROGRESS.md` ("Super Flower LEADEX III GOLD UP..." - product id 16593, confirmed to exist
verbatim in `products.name` today).

**Primary recommendation:** Treat 01-01/01-02/01-03/01-04 as four small, mostly-additive diffs on
top of already-mostly-safe defaults, not a rewrite. Do not add a rate-limiting or security-header
dependency that assumes Redis or a multi-worker deployment - this app runs single-process, and the
Phase 3 target is one small Oracle VM. Do not tighten the CSP `script-src`/`style-src` beyond
`'unsafe-inline'` this phase: the frontend has 16+ verified inline `onclick=`/`style=` attributes
that a strict policy would silently break, reintroducing exactly the "silent frontend failure" class
of bug this project has been bitten by three times already (per `PROGRESS.md`).

## User Constraints

No `CONTEXT.md` exists for this phase - the owner approved the roadmap directly (per
`ROADMAP.md`/`STATE.md`). The locked decisions below come from `ROADMAP.md`'s "Decisions Needed from
Owner" preamble, `STATE.md`'s Accumulated Context, and `PROJECT.md`'s Key Decisions table, and carry
the same authority as a CONTEXT.md for planning purposes.

### Locked Decisions
- Hosting is Oracle Cloud Always Free (ARM, Mumbai region), Cloudflare free tier in front. Budget is
  near zero - prefer no paid services. Sentry's free tier is the one acceptable exception (Phase 3,
  OPS-08 - not this phase). **Implication for this phase:** do not recommend any dependency that
  requires a paid service or an extra piece of infrastructure (e.g. Redis for rate-limit storage).
- Scraping moves to a Chrome extension in Phase 2; Airflow is replaced by a small worker process.
  **Implication for this phase:** OPS-05/OPS-06 must be written as plain, DB-only functions with no
  Airflow-specific dependency, only wired into the DAG for now (`dags/scheduled_scraper_dag.py`) so
  Phase 2's worker can call the same functions directly later.
- No price alerts or notification channels, ever (owner's decision, 2026-08-17). Not directly
  relevant to this phase's requirements, but any new user-facing messaging (e.g. staleness warnings)
  must not evolve into an alerting feature.
- **Grounding rule (the phase's organizing principle):** an absent value beats a wrong one. A fit
  check with missing data must say "unverified," never pass silently. This is FIT-01/02/03's mandate
  verbatim, and is independently confirmed already logged as a decision in `PROJECT.md` line 92:
  "An unverified fit check is its own state, never shown as passed" (Decided, as recommended).

### Team / File Ownership (locked, from the task brief and `.claude/agents/*.md`, both read directly)
- **web-dev** owns `src/api/`, `src/static/`, `src/services/compatibility_engine.py`,
  `src/services/compatibility_rules.py`, and `tests/test_frontend_e2e.py`,
  `tests/test_compatibility_rules.py`, `tests/test_image_proxy.py` [VERIFIED:
  `.claude/agents/web-dev.md`, read directly, 2026-09-24].
- **data-engineer** owns `src/scrapers/`, `src/matching/`, `src/services/` (except compatibility),
  `src/db/`, `scripts/`, `dags/`, and `tests/test_matching.py` plus new `tests/test_*.py` files
  [VERIFIED: `.claude/agents/data-engineer.md`, read directly, 2026-09-24].
- Every requirement in this research maps cleanly to one owner - no requirement's natural
  implementation crosses the ownership line. The one file both `01-02` and `01-03` touch
  (`src/api/main.py` for 01-02's exception handlers, `src/static/app.js` for 01-03) is within
  web-dev's own sequential plans, not a cross-agent conflict - ROADMAP.md already sequences them
  (01-02 after 01-01, 01-03 after 01-02) for exactly this reason.

### Claude's Discretion
- Exact CSP directive values beyond the mandatory `frame-ancestors 'none'` (see Pattern 2, Pitfall 1).
- Whether the three-state verdict string is computed server-side or client-side (see Assumption A4).
- Whether to add the optional image-proxy streaming hardening (Pitfall 6) - not required by the
  literal SEC-04 test.
- The exact 8th benchmark case and the precise wording of `benchmark_provider.py`'s CLI interface.

### Deferred Ideas (OUT OF SCOPE this phase)
- HSTS header (explicitly the Phase-3 proxy's job - see Pitfall 2).
- Full per-model `sitemap.xml` entries and server-rendered model pages (SEO-02..SEO-06, Phase 5).
- Agent-endpoint schema exclusion (SEC-06's "agent endpoints never appear in any public schema"
  clause - no agent endpoints exist until Phase 2, AGENT-04).
- Migrating inline `onclick=`/`style=` attributes to `addEventListener`/external CSS to allow a
  stricter CSP - legitimate future hardening, not required by this phase's literal text.
- `.env` file permissions on the VM (mode 600, owned by service user) - no VM exists until Phase 3.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| SEC-01 | CORS no longer allows `*` with credentials; unlisted `Origin` gets no ACAO header | Pattern 3 (Standard Stack alternatives), Code Examples "CORS with an explicit allow-list"; current state verified at `src/api/main.py:18-24` |
| SEC-02 | App refuses to start without `DATABASE_URL`; no credential in source | Verified default credential at `src/configs/settings.py:74-77`; fix is a 3-line change (raise if unset) |
| SEC-03 | Per-IP rate limits, tighter on `/images`, `/builder/*`, save-build; 429 with JSON body | Pattern 3 (`slowapi` + Cloudflare-aware key function), Package Legitimacy Audit, Pitfall 3 (CF-Connecting-IP trust boundary) |
| SEC-04 | Image proxy refuses >5MB / non-`image/*`, serves placeholder | Verified already-functional check at `src/api/routes/images.py:31,105`; Pitfall 6 (post-hoc vs streaming); gap is test coverage only |
| SEC-05 | Security headers incl. CSP with `frame-ancestors 'none'`; prod proxy adds HSTS | Pattern 2 (headers middleware), Pitfall 1 (CSP vs inline `onclick`/`style`), Pitfall 2 (HSTS deferred) |
| SEC-06 | `/docs`,`/redoc`,`/openapi.json` off in production | Pattern 1 (environment-gated construction); verified no `ENV` concept exists anywhere today |
| SEC-07 | Save-build rejects >20 ids, unknown ids, bodies >10KB | Verified unknown-ids check already exists at `src/api/routes/builder.py:249-252`; Pitfall 4 (body-size dependency, refuting a hallucinated Starlette API), Pitfall 5 (>20 check is new but cheap) |
| SEC-08 | `.env.example` matches `settings.py`/compose, tested | Verified complete env-var inventory from `settings.py` (11 vars) and `docker-compose.yml` (5 vars) read directly |
| WEB-01 | Branded 404 for pages; JSON 404 for `/api/*` | Pattern 4; verified `/api/*` JSON 404 already works via FastAPI's default `http_exception_handler` |
| WEB-02 | Generic 500, no traceback | Pattern 4; verified Starlette's `debug=False` default already strips tracebacks (`ServerErrorMiddleware.error_response` source read directly) |
| WEB-03 | Full Playwright suite passes; skip = fail | Environment Availability (chromium confirmed installed and working this session); Validation Architecture (wrapper/CI check needed) |
| WEB-04 | 375px e2e: search, picker, add part, verdict, compare | Verified exact selectors (`#search-input`, `#slots-container`, `#select-modal`, `#compatibility-status`) from `index.html`/`test_frontend_e2e.py`; Pitfall 1 (CSP must not break these) |
| WEB-05 | Footer links to About/Privacy with required disclosures | Verified current footer only partially covers this (`index.html:174-183`); Assumption A5 / Open Question 3 (contact address not yet decided) |
| FIT-01 | Missing-data rule -> named `unverified` item | Pattern 5, full nullable-field table for all 9 `RULES`; verified root cause at `compatibility_engine.py:221-223` |
| FIT-02 | Exactly 3 verdict states | Pattern 5; verified current 2-state UI at `app.js:794-800` and schema at `domain/builder.py:32-37` |
| FIT-03 | Wattage estimate names the part using a default | Pattern 6; verified `DEFAULT_CPU_TDP`/`DEFAULT_GPU_TDP` silent substitution at `compatibility_rules.py:92-93`, `compatibility_engine.py:263-264` |
| SEO-01 | Title/meta/OG/favicon/canonical; robots.txt/sitemap.xml 200 | Code Examples (minimal stub); verified current `<head>` has none of these at `index.html:1-8` |
| OPS-05 | Per-store freshness check names the store | Pattern 7; verified current check is global-only at `dags/scheduled_scraper_dag.py:243-260` |
| OPS-06 | 0 extractions with backlog>0 fails loudly | Pattern 7; verified extraction stage swallows all exceptions with no return value at `dags/scheduled_scraper_dag.py:115-125` and `scripts/extract_gpu_titles_groq.py` |
| AI-01 | `benchmark_provider.py` committed, 8-case PSU, scores/titles-per-min/JSON-failures, no DB writes | Pattern 8; "Reconstructing the AI-01 benchmark" section (original cases confirmed unrecoverable; real replacement candidates identified via live DB query) |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CORS policy, security headers, rate limiting | API / Backend | — | All three are FastAPI middleware; no browser-side or CDN component exists yet (Cloudflare/Caddy arrive in Phase 3) |
| Docs off in production, save-build validation | API / Backend | — | Enforced at app construction / route level in `src/api/main.py`, `src/api/routes/builder.py` |
| Image proxy caps (size/content-type) | API / Backend | — | Already server-side (`src/api/routes/images.py`); no client change needed |
| `.env.example` / no default DB credential | API / Backend | Database / Storage | Config lives in `src/configs/settings.py`; DB connection string is the specific secret at risk |
| 404/500 pages | API / Backend | Browser / Client | FastAPI serves the HTML file; the file's content is a Browser-tier artifact |
| About/Privacy pages, SEO meta/robots/sitemap-stub | API / Backend | Browser / Client | Static files served by FastAPI (`src/static/`); no SSR templating exists yet (that's Phase 5) |
| 375px builder e2e flow | Browser / Client | — | Playwright drives the rendered page; this is a test-infrastructure capability, not a new feature |
| Honest fit verdict (unverified state, 3-state summary) | API / Backend | Browser / Client | Verdict is computed in `CompatibilityEngine`/`BuilderService`; `app.js` only renders what the API returns |
| Wattage estimate naming | API / Backend | Browser / Client | Same split as above - `estimated_wattage` is computed server-side, displayed client-side |
| Per-store freshness check, backlog/extraction check | Database / Storage | — | Pure functions reading `price_history`/`products` via SQLAlchemy, invoked by the Airflow DAG (an orchestration layer sitting on top of the DB, not a web tier) |
| `scripts/measure_db_growth.py` (read-only) | Database / Storage | — | Direct Postgres size/growth queries; no web-tier involvement |
| `scripts/benchmark_provider.py` | N/A - standalone CLI script | — | Calls external LLM provider HTTP APIs directly via `GroqExtractionService`; touches neither the web app nor the database (AI-01 requires it write nothing to the DB) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| `slowapi` | 0.1.10 [VERIFIED: pypi registry - `pip index versions slowapi`, 2026-09-24] | Per-IP/per-token rate limiting on FastAPI routes | Thin wrapper around the `limits` library; the de-facto FastAPI rate-limiter referenced across current FastAPI security guidance [CITED: multiple 2026 blog posts and GitHub issues found via WebSearch, see Sources] |

No other new runtime dependency is needed for this phase. Security headers, the environment-gated
docs toggle, the body-size cap, and the branded error pages are all achievable with FastAPI/Starlette
APIs already present in `requirements.txt` (`fastapi>=0.115.0`; installed `0.140.0` per
`pip index versions fastapi` [VERIFIED: pypi registry, 2026-09-24], latest `0.141.1`).

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `slowapi` (in-memory) | `fastapi-limiter` (Redis-backed) | Correct across multiple worker processes, but requires a Redis service - this project has zero paid/extra infra in Phase 3 (Oracle Always Free, no Redis in the roadmap). Rejected for this phase. |
| Hand-rolled security-headers middleware | `Secweb` or `fastapi-security-headers` PyPI packages | Both exist and work, but the entire header set SEC-05 asks for is 4-5 lines of one function; a dependency adds a supply-chain surface for something this small. Rejected - hand-roll it (see Don't Hand-Roll below for the boundary between "trivial, hand-roll" and "subtle, use a library"). |
| Custom body-size ASGI middleware | A Starlette "built-in" body-size-limit middleware | **This does not exist.** A web search suggested `starlette.middleware.body_limit.RequestBodyLimitMiddleware`; this was checked against the installed package this session and refuted (see Pitfall below). Use a small per-route dependency instead. |

**Installation:**
```bash
pip install slowapi
# and add to requirements.txt / pyproject.toml
```

**Version verification:** `slowapi` 0.1.10 and `fastapi` 0.140.0 (installed) / 0.141.1 (latest)
confirmed via `pip index versions <package>` this session (2026-09-24). Training-data knowledge of
these libraries is generally current; the versions above are the checked ground truth.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `slowapi` | PyPI | latest release 2026-06-13 [VERIFIED: package-legitimacy seam, 2026-09-24] | unknown (seam could not resolve a download count) | `github.com/laurents/slowapi` | SUS (`unknown-downloads`) | Flagged - planner must add a `checkpoint:human-verify` task before `pip install slowapi` is added to `requirements.txt` |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `slowapi` - reason is a missing downloads signal, not a
missing-package or brand-new-package signal (the repo is real, `laurents/slowapi`, and it is the
package referenced repeatedly in current, dated FastAPI rate-limiting discussion found via
WebSearch). The package name itself is `[ASSUMED]` per the provenance rule (discovered via training
knowledge + WebSearch, not an authoritative source) despite passing the registry existence check.
**Before installing:** confirm the PyPI project page and GitHub repo by hand (they should match:
`pypi.org/project/slowapi`, `github.com/laurents/slowapi`), and pin an exact version in
`requirements.txt` rather than a floor (`slowapi==0.1.10`) so a future compromised release can't
silently substitute itself.

## Architecture Patterns

### System Architecture Diagram

```text
Browser (SPA, unchanged this phase)
   |
   |  HTTP request (any path, any origin)
   v
[NEW] CORSMiddleware (explicit origin allow-list, credentials off)
   |
   v
[NEW] Security-headers middleware (sets X-Content-Type-Options, Referrer-Policy, CSP on every response)
   |
   v
[NEW] slowapi Limiter (global default limit; tighter limits on /images, /builder/*)
   |          |
   |          +--> 429 JSON body if limit exceeded (short-circuits before reaching a route)
   v
Starlette routing
   |
   +--> /api/v1/*        -> existing routers (unchanged logic, SEC-07 adds a size/count gate on /builder/builds)
   |         |
   |         +--> unknown /api/* path -> FastAPI default HTTPException handler -> JSON 404 (ALREADY WORKS)
   |
   +--> /docs, /redoc, /openapi.json -> [NEW] only registered when ENV != "production"
   |
   +--> /  , /static/*   -> existing StaticFiles / FileResponse (unchanged)
   |
   +--> anything else    -> [NEW] path-aware 404 handler -> branded static/404.html
   |
   +--> unhandled exception anywhere above -> Starlette ServerErrorMiddleware
             |
             +--> debug=False (already the case) -> plain "Internal Server Error", no traceback (ALREADY WORKS)
             +--> [NEW] custom handler -> branded static/500.html (HTML) or {"detail": "..."} (JSON, for /api/*)

Compatibility verdict path (FIT-01/02/03), unchanged transport, changed payload:
POST /builder/validate -> BuilderService.validate_and_calculate_build()
   -> CompatibilityEngine.validate_build()
        -> for each Rule in RULES: _eval_rule(val_a, val_b)
             - both present, fails       -> CompatibilityWarning(level="error"/"warning")   [existing]
             - either value is None      -> [NEW] CompatibilityWarning(level="unverified", names the part)
        -> [NEW] wattage aggregate also records which CPU/GPU used a DEFAULT_*_TDP fallback
   -> BuildSummary { compatible, warnings[], [NEW] unverified_count, [NEW] verdict, estimated_wattage, [NEW] wattage_notes }
   -> app.js renders summary.verdict directly into #compatibility-status (3 states, not 2)

Freshness / backlog path (OPS-05/06), all pure functions reusable by Phase 2's worker:
Airflow DAG (dags/scheduled_scraper_dag.py)
   -> process_due_targets
   -> extract_canonical_identities  --[NEW]--> check_extraction_progress(backlog_before, backlog_after)
   -> extract_physical_specs
   -> apply_catalog_policy
   -> check_price_freshness (today: ONE global query) --[CHANGED]--> loops active stores, names each stale one
```

### Recommended Project Structure

No new top-level directories. New/changed files, grouped by the existing 4-plan split:

```
src/
├── configs/settings.py          # [CHANGED] add ENV, remove default DATABASE_URL credential
├── api/
│   ├── main.py                  # [CHANGED] CORS, docs toggle, security headers, limiter, 404/500 handlers
│   ├── deps.py                  # [OPTIONAL] rollback-on-exception in get_db (CONCERNS.md flagged this; small, safe to include)
│   └── routes/
│       ├── images.py            # [UNCHANGED logic] new tests for existing size/content-type checks
│       └── builder.py           # [CHANGED] save_build: >20 ids check, body-size dependency
├── services/
│   ├── compatibility_engine.py  # [CHANGED] _eval_rule third state, product_name on merged views, wattage naming
│   └── compatibility_rules.py   # [UNCHANGED] - the Rule dataclass and RULES list already generalize cleanly
├── domain/builder.py             # [CHANGED] CompatibilityWarning.level gains "unverified"; BuildSummary gains fields
└── static/
    ├── 404.html, 500.html        # [NEW]
    ├── about.html, privacy.html  # [NEW]
    ├── index.html                 # [CHANGED] <head> meta/OG/canonical/favicon, footer links
    └── app.js                     # [CHANGED] 3-state verdict rendering, wattage-estimate note

dags/scheduled_scraper_dag.py     # [CHANGED] per-store check_price_freshness, new check_extraction_progress
scripts/
├── measure_db_growth.py          # [NEW] read-only
└── benchmark_provider.py         # [NEW]

.env.example                      # [NEW]
tests/
├── test_compatibility_rules.py   # [CHANGED] add unverified-state coverage (web-dev owned)
├── test_image_proxy.py           # [CHANGED] add size/content-type tests (web-dev owned)
├── test_frontend_e2e.py          # [CHANGED] add 375px flow + mobile fixture (web-dev owned)
├── test_price_freshness.py       # [CHANGED] per-store cases (data-engineer owned)
└── test_benchmark_provider.py    # [NEW] offline scoring test (data-engineer owned)
```

### Pattern 1: Environment-gated app construction (SEC-06)

**What:** `ENV` does not exist anywhere in this codebase today [VERIFIED: `grep` across `src/configs/settings.py`, `docker-compose.yml`, `src/api/main.py` found zero matches for an `ENV`/`ENVIRONMENT` variable, 2026-09-24]. It must be added, then read once at app-construction time.

**When to use:** Any place a resource should exist in dev/test but not in production - here, `/docs`, `/redoc`, `/openapi.json`.

**Example:**
```python
# Source: fastapi.tiangolo.com (constructor parameters confirmed live via WebFetch, 2026-09-24)
# src/configs/settings.py
ENV = os.getenv("ENV", "development")

# src/api/main.py
_docs_enabled = settings.ENV != "production"
app = FastAPI(
    title="PC Builder API",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)
```
Setting `openapi_url=None` alone also disables `/docs` and `/redoc` (both depend on the schema), but
setting all three explicitly makes the test ("all three are off in production") a direct assertion
on each URL rather than an inference.

### Pattern 2: Security headers as one small middleware function (SEC-05)

**What:** A single `@app.middleware("http")` function that sets headers on every response after
`call_next`. No library needed - see Don't Hand-Roll.

**Example:**
```python
# Pattern confirmed against current FastAPI/Starlette middleware API [CITED: WebSearch results
# summarizing github.com/fastapi/fastapi#4420 and current blog write-ups, 2026-09-24]
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "   # see Pitfall: index.html has inline style= attributes
        "script-src 'self' 'unsafe-inline'; "  # see Pitfall: index.html has inline onclick= attributes
        "frame-ancestors 'none'; "
        "base-uri 'self'; object-src 'none'"
    )
    return response
```
**Do not add `Strict-Transport-Security` here** - see Pitfall (HSTS belongs to the Phase 3 proxy).

### Pattern 3: Rate limiting with a Cloudflare-aware, spoofing-safe key function (SEC-03)

**What:** `slowapi`'s default `get_remote_address` reads either the raw connection IP or
`X-Forwarded-For` depending on configuration, and either is wrong once Cloudflare is in front
[CITED: multiple sources via WebSearch, e.g. `medium.com/@amarharolikar/are-you-rate-limiting-the-wrong-ips-a-slowapi-story`,
2026-09-24 - MEDIUM confidence, third-party but consistent across independent sources]. Cloudflare's
own header is `CF-Connecting-IP`, which "will only be sent on the traffic from Cloudflare's edge to
your origin web server" and cannot be spoofed by a client **once the origin is reachable only through
Cloudflare** [CITED: developers.cloudflare.com/fundamentals/reference/http-request-headers, fetched
2026-09-24].

**When to use:** Now (Phase 1), so the rate-limit key function doesn't need to change again in
Phase 3. The Cloudflare-firewall guarantee (OPS-02) does not land until Phase 3, so document this as
an accepted interim limitation, not a Phase-1 blocker - the app is not publicly reachable yet.

**Example:**
```python
# src/api/main.py
from slowapi import Limiter
from slowapi.util import get_remote_address

def rate_limit_key(request: Request) -> str:
    # Trustworthy only once OPS-02 (Phase 3) firewalls direct access to the origin.
    # Until then this header is attacker-controlled if the app is ever exposed directly -
    # acceptable now because the app has no public URL yet.
    return request.headers.get("CF-Connecting-IP") or get_remote_address(request)

limiter = Limiter(key_func=rate_limit_key)
app.state.limiter = limiter
```
Do **not** additionally configure `uvicorn --proxy-headers --forwarded-allow-ips` for this - reading
the header directly in the key function is independent of uvicorn's own `request.client.host`
mechanism [CITED: uvicorn.dev/settings, WebSearch 2026-09-24] and needs no coordinated flag changes
across dev/test/Phase-3-prod.

**Worker-model caveat:** `slowapi`'s default storage is in-process memory (via the `limits`
library). If the API container is ever run with multiple uvicorn/gunicorn worker processes, each
process gets an independent counter and the effective limit multiplies by worker count. Recommend
running the API as a single process through this phase and Phase 3 (matches the "one small VM,
simple stack" plan) rather than adding Redis-backed storage. Document this constraint in
`.env.example` or `docs/DEPLOY.md` when Phase 3 writes the compose file.

### Pattern 4: Path-aware 404, and why 500 mostly already works (WEB-01, WEB-02)

**What is already true, verified this session against the installed packages:**
- `fastapi.exception_handlers.http_exception_handler` (installed FastAPI) always returns
  `JSONResponse({"detail": exc.detail}, status_code=exc.status_code)` regardless of path
  [VERIFIED: read `fastapi/exception_handlers.py` source directly, 2026-09-24]. So an unknown
  `/api/v1/whatever` path **already** gets a JSON 404 today with zero new code.
- `starlette.middleware.errors.ServerErrorMiddleware.error_response` returns
  `PlainTextResponse("Internal Server Error", status_code=500)` when `self.debug` is `False`
  [VERIFIED: read `starlette/middleware/errors.py` source directly, 2026-09-24]. `src/api/main.py`'s
  `FastAPI(...)` call does not pass `debug=True` [VERIFIED: full file read, 2026-09-24], so an
  unhandled exception today **already** returns no traceback and no framework name.

**What is missing:** a *branded* HTML 404 for non-API paths (today's default 404 is the same bare
JSON for every path, including `/some-typo-url`), and a *test* proving the 500 behavior (WEB-02
explicitly asks for "a test that raises inside a route").

**Example:**
```python
# src/api/main.py
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler

@app.exception_handler(StarletteHTTPException)
async def branded_404(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and not request.url.path.startswith("/api/"):
        return FileResponse(static_dir / "404.html", status_code=404)
    return await http_exception_handler(request, exc)  # unchanged JSON behavior for /api/* and other codes

@app.exception_handler(Exception)
async def branded_500(request: Request, exc: Exception):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Internal server error."}, status_code=500)
    return FileResponse(static_dir / "500.html", status_code=500)
```
This mirrors the existing `serve_index()` pattern (`FileResponse(static_dir / "index.html")`,
`src/api/main.py:38-40` [VERIFIED]) rather than introducing a new response style.

### Pattern 5: Three-state compatibility verdict (FIT-01, FIT-02)

**What exactly is missing, verified this session:**
```python
# src/services/compatibility_engine.py:221-223 (verbatim)
def _eval_rule(self, rule, val_a, val_b) -> CompatibilityWarning | None:
    if val_a is None or val_b is None:
        return None  # not enough data to check yet - not an error, just unknown
```
This `None` is indistinguishable, to both the API caller and `app.js`, from "checked and fine."
`domain/builder.py:20-22` (verbatim) already anticipates a third level in its own comment:
```python
class CompatibilityWarning(BaseModel):
    level: str         # "error", "warning", "info"
    message: str
```
`"info"` is declared but never produced by any of the 9 `RULES` [VERIFIED: read
`src/services/compatibility_rules.py` in full - only `"error"` and `"warning"` appear].

**Every rule in `RULES` and which of its two field inputs is nullable** [VERIFIED: read
`src/db/models/category_specs.py` in full, every referenced column is `Mapped[X | None]`]:

| # | slot_a.field_a | op | slot_b.field_b | level | Nullable side(s) |
|---|-----------------|----|-----------------|-------|-------------------|
| 1 | cpu.socket | eq | motherboard.socket | error | both (`CPUSpecs.socket`, line 35; `MotherboardSpecs.socket`, line 94) |
| 2 | ram.memory_type | eq | motherboard.memory_type | error | both (`RAMSpecs.memory_type`, line 112; `MotherboardSpecs.memory_type`, line 97) |
| 3 | ram.modules | le | motherboard.memory_slots | error | both (line 115; line 98) |
| 4 | ram.capacity_gb | le | motherboard.max_memory_gb | error | both (line 114; line 99) |
| 5 | cpu.socket | contains_in | cooler.supported_sockets | warning | `CoolerSpecs.supported_sockets` (line 179) - **only 21/585 cooler models have this filled** [CITED: STATE.md corrections + PROGRESS.md, cross-referenced this session] |
| 6 | gpu.length_mm | le | case.max_gpu_length_mm | error | `GPUSpecs.length_mm` (79→81 range, line 81) and `CabinetSpecs.max_gpu_length_mm` (line 160) - **~35% of live cabinet models have no clearance** [CITED: PROGRESS.md 2026-09-24, "820 of 1,404 live cabinet models (65%)"] - this is Success Criterion #1's exact scenario |
| 7 | cooler.height_mm | le | case.max_cooler_height_mm | error | both (line 182; line 161) - cooler height on 732 models per PROGRESS.md |
| 8 | cooler.aio_radiator_mm | le | case.max_radiator_mm | warning | `aio_radiator_mm` is a *derived* field (`None` on purpose for air coolers - not missing data, see Pitfall) and `max_radiator_mm` (derived from `CabinetSpecs.radiator_sizes`, line 164) - ~24% of cabinets missing per PROGRESS.md ("1,017 of 1,459", 70%) |
| 9 | motherboard.form_factor | form_factor_fits | case.form_factor | error | both (line 96; line 159) |

Plus the wattage aggregate (`compatibility_engine.py:262-283`, **not** in `RULES`, handled separately
- see Pattern 6) and two PSU-capacity warnings (lines 267-283) that are always `level="warning"` and
never flip `compatible`.

**Recommended minimal-diff design:**
1. `CompatibilityWarning.level` gains a fourth valid string: `"unverified"`.
2. `_merge()` (`compatibility_engine.py:49-66`) or its caller stamps a `product_name` onto each
   returned `SimpleNamespace`, e.g. by passing `p.name` alongside the existing per-product loop in
   each `_resolve_slot` branch. This is what lets the new unverified message *name the part*
   (Success Criterion #1: "names the case and the missing spec").
3. `_eval_rule` (or a thin wrapper around it) returns
   `CompatibilityWarning(level="unverified", message=f"Cannot verify {rule.slot_a}/{rule.slot_b}: {name} has no published {field}.")`
   instead of `None`, when exactly one side (not both, and not a legitimately-N/A derived field like
   `aio_radiator_mm` on an air cooler - see Pitfall) is missing.
4. `BuildSummary` (`domain/builder.py:32-37`) gains `unverified_count: int` and a server-computed
   `verdict: str` with exactly the three literal strings from FIT-02 ("Problems found" /
   "No problems found - N checks unverified" / "All checks passed"), computed once in
   `BuilderService`/`CompatibilityEngine.validate_build()` so the exact wording is unit-testable in
   Python and `app.js` does not duplicate the branching logic.
5. `app.js`'s existing `warningsEl.innerHTML = (summary.warnings || []).map(w => ...)` loop
   (`app.js:802-804`, verbatim: `` <div class="warning-item ${w.level}">${w.message}</div> ``)
   needs **no structural change** - a `level="unverified"` entry renders automatically with a new
   CSS class `warning-item unverified` that web-dev styles distinctly from `.error`/`.warning`.
6. `app.js`'s verdict block (`app.js:794-800`) changes from a 2-way `if` to a 3-way branch reading
   `summary.verdict` (or re-deriving the same 3-way logic from `compatible` + `unverified_count` if
   the team prefers not to add a `verdict` string field - either is consistent with the research;
   computing it server-side is recommended to avoid string-format drift).

### Pattern 6: Naming the wattage estimate (FIT-03)

**What exists today**, verified verbatim:
```python
# compatibility_rules.py:92-93
DEFAULT_CPU_TDP = 120
DEFAULT_GPU_TDP = 250

# compatibility_engine.py:263-264
cpu_watt = sum((self._get(c, "tdp") or DEFAULT_CPU_TDP) for c in selections.get("cpu", []))
gpu_watt = sum((self._get(g, "tdp") or DEFAULT_GPU_TDP) for g in selections.get("gpu", []))
```
This is a **separate code path** from the `RULES` loop (Pattern 5) - it lives 40 lines further down
in the same function, `validate_build`. A FIT-03 fix must touch this block specifically, not assume
the Pattern-5 change covers it.

**Recommended design:** while summing, also collect which named products used the fallback:
```python
wattage_notes = []
for c in selections.get("cpu", []):
    if self._get(c, "tdp") is None:
        wattage_notes.append(f"{self._get(c, 'product_name')}: no listed TDP, using typical {DEFAULT_CPU_TDP}W")
# same for gpu/DEFAULT_GPU_TDP
```
Add `wattage_notes: list[str]` (or similar) to `BuildSummary`; `app.js`'s
`wattageEl.innerText = ...` (line 806) gains a sibling element rendering these notes whenever the
list is non-empty.

### Pattern 7: Per-store freshness and loud backlog checks as plain functions (OPS-05, OPS-06)

**What exists today**, verified verbatim (`dags/scheduled_scraper_dag.py:238-260`):
```python
def price_data_is_stale(latest: datetime | None, now: datetime, max_age: timedelta = PRICE_MAX_AGE) -> bool:
    return latest is None or now - latest > max_age

def check_price_freshness():
    with SessionLocal() as session:
        latest = session.scalar(select(func.max(PriceHistory.scraped_at)))
    ...
    if price_data_is_stale(latest, now):
        raise RuntimeError(f"No price saved since {latest} - scraping has stalled.")
```
This is a **single global** check. `PriceHistory` has no `sid` column
[VERIFIED: read `src/db/models/price_history.py` in full]; store attribution requires a join through
`Product.sid` (confirmed used elsewhere, e.g. `src/services/builder_service.py:68`,
`src/api/routes/builder.py:151`). `price_data_is_stale` is already a pure function taking
`(latest, now)` - the existing test file (`tests/test_price_freshness.py`) already tests exactly this
shape and can be extended per-store with no change to the pure function itself:

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

**OPS-06 ("0 extractions with a backlog"):** `execute_canonical_extraction`
(`dags/scheduled_scraper_dag.py:115-125`, verbatim) swallows every per-category exception and never
returns a count:
```python
for label, fn in runners:
    try:
        fn(limit=limit_per_category)
    except Exception as e:
        print(f"[Canonical Extraction] {label} failed: {e}")
```
None of the 9 extractor functions (e.g. `extract_gpu_identity`,
[VERIFIED: read `scripts/extract_gpu_titles_groq.py` in full - the function has no `return`
statement at all]) report how many rows they processed. **Do not** thread return values through all
9 owned-by-data-engineer extractor scripts to fix this - measure backlog by counting DB state before
and after the whole stage instead, matching the existing per-category eligibility query already used
by every extractor (`stmt.where(Product.canonical_id.is_(None))`,
[VERIFIED: `scripts/extract_gpu_titles_groq.py:34-36`]):
```python
def count_backlog(session) -> int:
    categories = ("CPU", "Motherboard", "GPU", "Storage", "Power Supply", "CPU Cooler", "Cabinet", "Monitor", "RAM")
    return session.scalar(
        select(func.count()).select_from(Product)
        .where(Product.p_category.in_(categories), Product.canonical_id.is_(None))
    )

def check_extraction_progress(before: int, after: int):
    if before > 0 and after >= before:
        raise RuntimeError(f"0 extractions this cycle with a backlog of {before} (every provider likely exhausted).")
```
Wire `count_backlog()` before and after `execute_canonical_extraction()` in the DAG, and a new
`check_extraction_progress_task` after it (`trigger_rule="all_done"`, matching the existing
`freshness_task` pattern at `dags/scheduled_scraper_dag.py:313-319`).

### Pattern 8: `benchmark_provider.py` against the existing provider abstraction (AI-01)

**The exact interface to match**, verified verbatim (`src/services/groq_extraction_service.py`):
```python
# line 112-148
def provider_chain() -> list[tuple[str, str, str, str]]:
    """Providers to try in order, as (name, api_url, model, api_key), skipping any whose key is unset."""
    ...

# line 519
def extract_batch(self, system_prompt: str, titles: list[str], max_retries: int = 4) -> list[dict]:
```
and the constructor used by `default_service()` (line 619-632, verbatim):
```python
_name, api_url, model, api_key = chain[0]
return GroqExtractionService(api_key=api_key, model=model, api_url=api_url, timeout=timeout)
```
AI-01's literal text - "It runs against any `(name, url, model, key)` provider" - matches this tuple
shape exactly. `benchmark_provider.py` should accept this 4-tuple (via CLI args or by iterating
`provider_chain()` itself) and construct a `GroqExtractionService` directly per provider under test,
calling `extract_batch(PSU_IDENTITY_BATCH_PROMPT, titles)` with the **bare prompt constant**
(`PSU_IDENTITY_BATCH_PROMPT`, `groq_extraction_service.py:269-282`) rather than
`identity_prompt('psu')` - the latter appends live brand-hint data from the database, which would
make the benchmark non-reproducible and give it an unwanted DB dependency (AI-01 only requires it
write nothing to the DB, but a benchmark that also *reads* nothing is more portable, e.g. for the
Phase 8 desktop trial with no DB access at all).

The response schema to score against (verbatim from the prompt, `groq_extraction_service.py:270`):
```
{"results": [{"index": number, "brand": string, "model_number": string|null,
              "wattage": number|null, "efficiency_rating": string|null,
              "confidence": "high"|"medium"|"low", "notes": string|null}, ...]}
```
Score by comparing `efficiency_rating` per title against the answer key (the documented trap cases
are specifically about the certification-tier field - see Reconstructing the benchmark below).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-IP rate limiting with proper 429 semantics | A custom counter dict + manual `Retry-After` header math | `slowapi` | Sliding-window/fixed-window token-bucket correctness and thread-safety across concurrent requests are easy to get subtly wrong; `slowapi`/`limits` already handle it |
| CORS preflight handling | Hand-rolled `OPTIONS` responses and `Origin` echoing | Starlette's `CORSMiddleware` (already in use - it only needs correct configuration, not replacement) | Preflight caching headers (`Access-Control-Max-Age`), `Vary: Origin`, and the credentialed-vs-`*` rule are subtle enough that browsers silently reject a wrong hand-rolled combination with no server-side error to debug from |
| Request body size capping | Trusting the `Content-Length` header alone | A dependency that reads `await request.body()` and checks actual byte length | `Content-Length` can be absent or wrong for chunked transfer encoding; the actual byte count is the only trustworthy signal. (This is a 4-line dependency, not a library - see Pattern in Code Examples.) |
| The "unverified" compatibility state | A parallel rule-authoring system or a second pass over `RULES` | Extend `CompatibilityWarning.level` and `_eval_rule`'s existing None-check | The existing declarative `RULES` list plus `_eval_rule`'s pairwise iteration already generalizes across all 9 rules; a parallel system would duplicate `validate_build`'s and `filter_candidates`'s iteration logic |
| AI-01's answer key | Inventing "plausible" PSU titles/tiers, or trusting the current `psu_title_extractions.efficiency_rating` value as ground truth | Real catalog titles cross-checked against the 80 PLUS official registry (`data/raw/All_certified_psus.xlsx`, already imported by `scripts/import_80plus_efficiency.py`) or the manufacturer's own product page | Trusting the LLM's own past output as the benchmark's answer key is circular - it would score the model against itself. See Reconstructing the benchmark below. |

**Key insight:** every piece of "don't hand-roll" guidance in this phase is really the same insight
in four disguises - a check that looks like arithmetic (rate-limit windows, body-size counting,
compatibility pass/fail, benchmark scoring) usually has an edge case someone already got wrong once
and fixed properly (a library) or the project already got wrong once and fixed properly (the
existing `RULES`/`_eval_rule` design, the existing 80 PLUS registry). Reuse the fix, don't redo the
mistake.

## Common Pitfalls

### Pitfall 1: A strict CSP `script-src`/`style-src` will silently break the frontend
**What goes wrong:** Adding `Content-Security-Policy: script-src 'self'` (no `'unsafe-inline'`)
silently disables every inline `onclick="..."` handler and inline `style="..."` attribute in the
page. Buttons stop responding; the page loses layout. Neither necessarily throws a JS error the
existing e2e no-console-errors test would catch (a CSP violation is logged to the console as a
warning/error depending on browser and directive, but the *symptom* - a dead button - could pass a
naive check).
**Why it happens:** `src/static/index.html` has 7 verified inline `onclick=` attributes
[VERIFIED: `grep -c 'onclick=' src/static/index.html` = 7, e.g. lines 151, 154, 191, 214, 224] plus
9 more generated by `app.js` template strings (e.g. `app.js:514`,
`` onclick="openCompareModal('${escapeHtml(m.name)}', ${c.id})" ``), and multiple inline `style=`
attributes (`index.html:136-158`, e.g. `` style="display: flex; justify-content: space-between;..." ``).
**How to avoid:** Include `'unsafe-inline'` in both `script-src` and `style-src` this phase. SEC-05's
literal text only requires the CSP *include* `frame-ancestors 'none'` - it does not require a fully
strict policy. Tightening `script-src`/`style-src` by migrating to `addEventListener` and external
CSS classes is legitimate future work, out of scope here.
**Warning signs:** the 375px e2e test (WEB-04) and `test_no_console_errors_on_load` (WEB-03) are the
safety net - run them after adding the CSP header, not just after adding the middleware in isolation.

### Pitfall 2: HSTS set by the app itself can poison local dev browsers
**What goes wrong:** `Strict-Transport-Security` is a browser-side, per-hostname cache. If a
developer's browser ever receives this header from `http://127.0.0.1:PORT` (Playwright's Chromium
instance is fresh each run and unaffected, but a developer's own long-lived Chrome profile is not),
that browser will refuse plain-HTTP connections to that host/port for the `max-age` duration.
**Why it happens:** SEC-05's literal text assigns this specifically to "the production proxy," and
Phase 3's roadmap confirms Caddy/Cloudflare, not this FastAPI app, is meant to add it.
**How to avoid:** Do not add `Strict-Transport-Security` in the Phase-1 security-headers middleware.
Leave it to Phase 3's Caddy config, which only ever serves over the real domain.

### Pitfall 3: Trusting `CF-Connecting-IP` before the origin is actually firewalled
**What goes wrong:** Until Phase 3's OPS-02 firewall restricts inbound traffic to Cloudflare's IP
ranges, a request that reaches the origin directly (bypassing Cloudflare) can set an arbitrary
`CF-Connecting-IP` header itself, defeating or weaponizing the rate limiter.
**Why it happens:** Cloudflare's spoofing protection is a property of the network path
("only sent on traffic from Cloudflare's edge to your origin"), not of the header name itself
[CITED: developers.cloudflare.com, fetched 2026-09-24].
**How to avoid:** Accept this as a documented, deferred risk in Phase 1 - the app has no public URL
yet, so there is no live attacker who could reach the origin directly. Do not treat it as a Phase-1
blocker; do note it in `docs/DEPLOY.md` or a code comment so Phase 3 doesn't forget the firewall step
is load-bearing for this specific design choice.

### Pitfall 4: A hallucinated Starlette API for body-size limiting
**What goes wrong:** A plausible-sounding class, `starlette.middleware.body_limit.RequestBodyLimitMiddleware`,
appears in web-search summaries of "how to limit request body size in FastAPI." **It does not exist**
in the installed package.
**Why it happens:** Verified this session by direct import against the installed Starlette 1.3.1:
```
>>> from starlette.middleware.body_limit import RequestBodyLimitMiddleware
ModuleNotFoundError: No module named 'starlette.middleware.body_limit'
```
[VERIFIED: ran this exact import against the project's installed `starlette==1.3.1`, 2026-09-24].
The real middleware directory contains only `authentication.py, base.py, cors.py, errors.py,
exceptions.py, gzip.py, httpsredirect.py, sessions.py, trustedhost.py, wsgi.py`.
**How to avoid:** Use the small dependency pattern in Pattern/Code Examples instead
(`await request.body()` length check). This is also confirmed safe to double-read: Starlette's
`Request.body()` caches to `self._body` on first read and `Request.json()` reuses that cache
[VERIFIED: read `starlette/requests.py` source for both methods directly, 2026-09-24] - so reading
the body once in a dependency does not break FastAPI's own subsequent Pydantic-model parsing of the
same request.

### Pitfall 5: SEC-07's "more than 20 product ids" is not currently reachable, but still needs the explicit check
**What goes wrong:** A planner reading `save_build`'s current code might conclude the 20-id check is
unnecessary, since `SaveBuildRequest.selections: dict[str, int]` is validated against
`SLOT_CATEGORY`'s 9 known keys (`unknown_slots = set(selections) - set(SLOT_CATEGORY)` at
`builder.py:244-246`), making more than 9 *meaningful* entries structurally impossible today.
**Why it happens:** A dict can't have duplicate keys, and any extra key not in `SLOT_CATEGORY`'s 9
entries is already rejected as an "unknown slot" before an id-count check would even run.
**How to avoid:** Implement the explicit `len(selections) > 20` check anyway, before the DB lookup.
It costs one line, satisfies the literal requirement text and its test, and is forward-compatible
with a future where a slot can hold more than one item (e.g. two RAM sticks as separate line items).

### Pitfall 6: The image proxy's 5 MB cap is enforced *after* the full body is downloaded
**What goes wrong:** `images.py:105` (verbatim) - `` len(r.content) > MAX_BYTES `` - only rejects an
oversized image after `httpx` has already buffered the entire response body into memory via
`r.content`. SEC-04's literal test ("refuses bodies over 5 MB... serving the placeholder instead")
**already passes** with this code as-is (the placeholder IS served for an oversized body) - this is
a memory-exhaustion hardening note, not a test-failure risk.
**Why it happens:** `httpx.Client.get()` reads the full response before the calling code can inspect
its size, unless streaming is used.
**How to avoid:** Optional for this phase (the literal SEC-04 test is already satisfiable); if time
allows, switch to `client.stream("GET", u)` and abort after `MAX_BYTES` bytes have been read. Do not
let this optional hardening block the phase - the required test only needs the placeholder to be
served, which the current code already does.

### Pitfall 7: The wattage-naming fix (FIT-03) and the unverified-state fix (FIT-01/02) are different code paths
**What goes wrong:** Implementing Pattern 5 (the `RULES`/`_eval_rule` change) and assuming FIT-03 is
automatically covered.
**Why it happens:** Both live in `CompatibilityEngine.validate_build()`, but the wattage aggregate
(`compatibility_engine.py:262-283`) is explicitly commented as "handled separately from RULES"
(`compatibility_rules.py:90`, verbatim: `` # Wattage is an aggregate (sum), not a pairwise rule -
kept separate from RULES. ``) and never calls `_eval_rule`.
**How to avoid:** Treat FIT-03 as its own small addition (Pattern 6), reviewed and tested separately
from FIT-01/02.

### Pitfall 8: `aio_radiator_mm` being `None` on an air cooler is not "missing data" - it's N/A
**What goes wrong:** A naive implementation of the new "unverified" state might flag every air
cooler's radiator-fit check as unverified, since `cooler.aio_radiator_mm` is always `None` for them.
**Why it happens:** `compatibility_engine.py:177` sets this field deliberately: `` v.aio_radiator_mm
= v.radiator_size_mm if (v.cooler_type or "").upper().startswith("AIO") else None `` - `None` here
means "this rule does not apply to this product," not "we don't know the value."
**How to avoid:** The unverified-state logic must distinguish a **derived, intentionally-N/A** field
(`aio_radiator_mm` on air coolers) from a **genuinely-missing-data** field (e.g.
`case.max_gpu_length_mm` when the cabinet hasn't been page-read yet). The existing rule comment
(`compatibility_rules.py:59-62`) already documents which fields are which - use that as the source
of truth, not a blanket "if None, unverified" rule.

### Pitfall 9: Never invent or self-verify the benchmark's answer key
**What goes wrong:** Building `benchmark_provider.py`'s 8 test cases from the current
`psu_title_extractions.efficiency_rating` values would score every provider against whatever the
project's own LLM pipeline already believes - a circular check that cannot detect a systematic error
repeated across providers.
**Why it happens:** The temptation is to "reconstruct" by just reading today's DB values, since they
happen to already be correct for the specific rows found this session (see below).
**How to avoid:** Independently confirm each of the 8 answers against the 80 PLUS official registry
export (`data/raw/All_certified_psus.xlsx`) or the manufacturer's own retail listing/spec page before
locking the answer key into the script - exactly the process `scripts/import_80plus_efficiency.py`
and `PROGRESS.md`'s "80 PLUS registry match agrees on 94 and disagrees on 25" audit already
established as this project's standard of evidence for a PSU certification claim.

## Code Examples

### Disabling `/docs`, `/redoc`, `/openapi.json` conditionally
```python
# Source: fastapi.tiangolo.com (constructor parameters), confirmed live 2026-09-24
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)  # fully off
# or conditionally, see Pattern 1
```

### CORS with an explicit allow-list and no credentials
```python
# This app has no cookies/sessions anywhere [VERIFIED: full read of src/api/main.py,
# src/api/deps.py, src/api/routes/builder.py - no Set-Cookie, no session middleware, share
# tokens are passed as URL path segments, not cookies]. There is no legitimate need for
# allow_credentials=True.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,  # [] until a real domain exists; explicit list after
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

### Body-size-capping dependency (replaces the non-existent Starlette middleware)
```python
# Verified safe against installed starlette==1.3.1: Request.body() caches to self._body,
# and Request.json() (which FastAPI's automatic Pydantic parsing uses) reuses that cache -
# reading the body here does not consume it for the route's own parsing.
async def cap_body_size(request: Request, max_bytes: int = 10_000) -> None:
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail="Request body too large.")

@router.post("/builds", dependencies=[Depends(cap_body_size)])
def save_build(req: SaveBuildRequest, db: Session = Depends(get_db)):
    ...
```

### Minimal `robots.txt` / `sitemap.xml` stub for Phase 1 scope
```python
# SEO-01 only requires these return 200 this phase; SEO-04 (Phase 5) adds real per-model
# entries. A minimal valid stub avoids over-building.
ROBOTS_TXT = "User-agent: *\nDisallow:\nSitemap: /sitemap.xml\n"

@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return Response(ROBOTS_TXT, media_type="text/plain")

@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>/</loc></url></urlset>'
    return Response(xml, media_type="application/xml")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `allow_origins=["*"]` + `allow_credentials=True` | Explicit origin allow-list + `allow_credentials=False` | This phase | Closes an active CSRF/credential-leak-shaped hole even though no credentials exist yet - closes it before any are added |
| Missing data treated as an implicit pass | Missing data is its own "unverified" state, distinct from pass/fail | This phase (owner decision logged 2026-08-17 per REQUIREMENTS.md "Out of Scope" note and confirmed 2026-09-24 in `PROJECT.md` line 92: "An unverified fit check is its own state, never shown as passed") | Same class of "grounding" discipline the project already applies to spec extraction (verbatim-quote requirement) now applied to the compatibility engine |
| A single global "has any price been saved" freshness check | Per-store freshness, naming the stale store | This phase | Directly actionable: today's failure message can't tell you *which* of 10 stores broke |
| `slowapi`'s common misconception: "it reads the real client IP automatically" | It reads either the raw connection or `X-Forwarded-For`, and either can be wrong/spoofable behind a proxy without an explicit trusted-header key function | Not new to this phase, but worth correcting explicitly since Cloudflare is a locked Phase-3 decision | Avoids shipping a rate limiter that either rate-limits everyone as one client (proxy IP) or trusts a spoofable header with no plan to firewall it |

**Deprecated/outdated:** none of this project's own prior patterns are deprecated by this phase;
this phase closes gaps rather than replacing working approaches.

## Reconstructing the AI-01 benchmark (special section - see also Pitfall 9)

**Confirmed absent from history:** an exhaustive search this session found no trace of the original
8 titles/answers as data:
```bash
git log --all -p --diff-filter=A -- "*benchmark*"      # no results
git log --all --oneline | grep -i "bench"               # only the two commits discussed below
git log --all -p -S"Super Flower" --oneline              # only prose mentions in PROGRESS.md/tests
find . -iname "*benchmark*"                              # nothing
```
[VERIFIED: all four commands run this session against the full local git history, 2026-09-24]. The
only surviving evidence is prose in `PROGRESS.md` (2026-09-20/21 sections) and one test docstring
(`tests/test_matching.py:448`, `` "took a fixed 8-case benchmark from mixed to 8/8..." ``) - aggregate
scores only, never the underlying titles or a scoring function.

**Real candidates found this session** (read-only queries against the live `pc_builder_postgres`
container, 2026-09-24 - **each answer below must still be independently re-confirmed against the 80
PLUS registry or the manufacturer's page before being locked into the script**, per Pitfall 9):

| Product id | Title (verbatim from `products.name`) | Trap being tested | Current DB answer |
|---|---|---|---|
| 16593 | "Super Flower LEADEX III GOLD UP ATX 3.1 750W Cybenetics Platinum Certified Gold SMPS Power Supply" | The exact Cybenetics-vs-80-PLUS trap quoted in `PROGRESS.md` line 829 - title states both "Cybenetics Platinum" and "Gold" | `80+ Gold` |
| 3960 | "MSI MAG A750GL PCIE5 ATX 3.1 Fully Modular SMPS MAG-A750GL-PCIE5" | MSI's "GL" suffix = Gold, not stated as a word | `80+ Gold` |
| 20457 / 17180 | "MSI MAG A850GL PCIE5..." (two listings) | Same MSI "GL" inference at a different wattage | `80+ Gold` |
| 16759 / 18924 / 14917 | "MSI MAG A650BN 650 Watt 80 Plus Bronze Power Supply" (three listings) | MSI's "BN" suffix = Bronze | `80+ Bronze` |
| 6186 | "Corsair RM750E 750 Watt Cybenetics Gold Fully Modular ATX 3.1 Power Supply" | A *non-trap* control: here Cybenetics Gold and 80 PLUS Gold happen to agree - tests that a model doesn't over-correct by assuming Cybenetics never matches | `80+ Gold` |
| 16673 / 19204 | "Cooler Master MWE Gold 850..." | Model name states the tier directly (documented "manufacturer's own marker" case) | `80+ Gold` |
| 15310 | "Thermaltake Toughpower GF A3 750W 80+ Gold PCIe Gen5 ATX 3.0 Fully Modular PSU" | Explicitly stated in title - sanity/control case, no inference needed | `80+ Gold` |

Seven strong, independently-checkable candidates plus a control were found; AI-01 needs 8 with real
diversity (recommend adding one deliberately **untiered** title - PROGRESS.md documents that "the
remaining 48 pages state no rating at all" is often the *correct* answer, i.e. `null`, not a guess -
to test that the model doesn't invent a tier when none exists).

**Live DB baseline gathered this session** (read-only, useful for `scripts/measure_db_growth.py`'s
design, OPS-07): database size **127 MB**; `price_history` **386,301 rows** spanning
**2026-07-27 to 2026-09-24** (59 days, ≈6,548 rows/day average); `products` **12,876 rows**
[VERIFIED: `docker exec pc_builder_postgres psql` read-only queries, 2026-09-24].

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | `slowapi`'s default 429 JSON error body shape (exact field names) was not verified against installed source (package is not installed in this environment) | Standard Stack / Pattern 3 | Low - the executor installs it and can inspect the actual response; SEC-03's test only requires *a* JSON body, not a specific shape |
| A2 | The recommended CSP policy string (`default-src 'self'; img-src 'self' data:; ...`) is a starting point, not verified against every static asset the page loads | Pattern 2 | Low-medium - if any third-party font/script is loaded (none found this session, but not exhaustively grepped for every asset URL), the policy would need a matching `*-src` addition; the required e2e/console tests will catch this |
| A3 | `Secweb`/`fastapi-security-headers` were characterized as unnecessary for this phase's small header set, based on WebSearch summaries of their scope, not a direct read of either package's source | Standard Stack alternatives | Low - this is a build-vs-buy judgment call, not a correctness risk either way |
| A4 | The recommended `verdict: str` field computed server-side (Pattern 5, item 4) is this research's design suggestion, not something REQUIREMENTS.md mandates as a literal schema field - the requirement only mandates the three literal *display* strings exist somewhere | Pattern 5 | Low - an equally valid design computes the same three strings client-side from `compatible` + `unverified_count`; either satisfies FIT-02 |
| A5 | The contact-address content required by WEB-05 has no value yet - ROADMAP.md's "Decisions Needed from Owner" table lists "Contact email for the About page" as still open (recommendation: a dedicated address on the new domain, not yet chosen) | Architecture Patterns / WEB-05 | Medium - the About page cannot ship its final copy without this; recommend a placeholder plus a `checkpoint:human-verify`-style flag in the plan rather than blocking the whole plan on it |

**If this table is empty:** N/A - see rows above.

## Open Questions

1. **Exact `slowapi` 429 response shape**
   - What we know: `slowapi` raises `RateLimitExceeded`, which by convention gets mapped to a JSON
     error response via `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)`.
   - What's unclear: the precise default field names in that body (not verified against source this
     session - package not installed).
   - Recommendation: confirm hands-on at install time; SEC-03's test only requires the body be JSON,
     so this doesn't block planning.

2. **Whether `.env` file permissions (mode 600, owned by service user) are testable in Phase 1**
   - What we know: SEC-08 mentions this, but the referenced VM doesn't exist until Phase 3 (Oracle
     Always Free, OPS-01).
   - What's unclear: whether this clause should produce a Phase-1 deliverable at all.
   - Recommendation: treat the `.env.example` + settings.py/compose cross-check as the Phase-1
     deliverable; defer the file-permission assertion to Phase 3's `docs/DEPLOY.md`/runbook, where an
     actual VM exists to set permissions on.

3. **Contact email for WEB-05's About page**
   - What we know: not yet decided (see Assumption A5); Cloudflare Email Routing on the new domain
     is the recommendation in ROADMAP.md, but the domain itself isn't purchased yet either.
   - What's unclear: what to literally print on the About page today.
   - Recommendation: use a clearly-marked placeholder (e.g. a note that a dedicated contact address
     is pending domain registration) so the page ships now and gets a one-line update in Phase 3
     rather than blocking WEB-05 entirely on an unrelated owner action.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (`pc_builder_postgres` container) | OPS-05, OPS-06, OPS-07, all DB-backed tests | Yes [VERIFIED: `docker ps`, healthy, 2026-09-24] | postgres:15-alpine | — |
| Airflow (`pc_builder_airflow` container) | OPS-05, OPS-06 (DAG wiring) | Yes [VERIFIED: `docker ps`, up 4 days] | apache/airflow:2.9.1-python3.11 | — |
| Playwright + Chromium | WEB-03, WEB-04 | Yes [VERIFIED: launched chromium 148.0.7778.96 directly this session] | 148.0.7778.96 | — |
| `slowapi` (PyPI) | SEC-03 | Not yet installed [VERIFIED: `pip show slowapi` -> not found] | latest 0.1.10 on PyPI | none needed - trivial to add |
| Non-browser test suite | all `tests/test_*.py` except e2e | Yes, 309 tests collected [VERIFIED: `pytest --collect-only`, matches the 309 figure given in the task brief exactly] | pytest 8.4.0+ | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `slowapi` is simply not yet installed; no fallback needed,
just an install step (flagged `[SUS]` above - gate behind `checkpoint:human-verify`).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.0+ (installed), Playwright sync API for e2e |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| Quick run command | `python -m pytest -q tests --ignore=tests/test_frontend_e2e.py` (309 tests today, seconds) |
| Full suite command | `python -m pytest -q tests` (includes Playwright, ~6 min per task brief) |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| SEC-01 | Unlisted `Origin` gets no `Access-Control-Allow-Origin` | unit (TestClient) | `pytest tests/test_cors.py -x` | Wave 0 - new file |
| SEC-02 | App refuses to start without `DATABASE_URL`; no `pc_builder123` in source | unit + grep | `pytest tests/test_settings.py -x`; `grep -r pc_builder123 src/` (expect empty) | Wave 0 - new file |
| SEC-03 | Over-limit request returns 429 JSON | unit (TestClient, low limit override) | `pytest tests/test_rate_limits.py -x` | Wave 0 - new file |
| SEC-04 | Oversized/wrong-content-type image -> placeholder | unit | `pytest tests/test_image_proxy.py -x` | Extend existing (web-dev owned) |
| SEC-05 | Headers present on HTML responses; CSP includes `frame-ancestors 'none'` | unit (TestClient headers) | `pytest tests/test_security_headers.py -x` | Wave 0 - new file |
| SEC-06 | `/docs`, `/redoc`, `/openapi.json` 404 when `ENV=production` | unit (env-var override) | `pytest tests/test_docs_disabled.py -x` | Wave 0 - new file |
| SEC-07 | >20 ids / unknown ids / >10KB body all rejected | unit | `pytest tests/test_builder_validation.py -x` | Wave 0 - new file (unknown-ids path already works, needs a test) |
| SEC-08 | `.env.example` covers every var in `settings.py` + compose files | unit (parse + diff) | `pytest tests/test_env_example.py -x` | Wave 0 - new file |
| WEB-01 | Bad page -> branded HTML 404; bad `/api/*` -> JSON 404 | unit | `pytest tests/test_error_pages.py -x` | Wave 0 - new file (API JSON 404 already works by default) |
| WEB-02 | Route that raises -> generic 500, no traceback | unit (route that raises) | `pytest tests/test_error_pages.py -x` | same new file as WEB-01 |
| WEB-03 | Full Playwright suite passes; skip = fail | e2e + process | `python -m pytest -q tests/test_frontend_e2e.py` + a wrapper/CI check for skip count | Existing file; wrapper is new |
| WEB-04 | 375px flow: search -> picker -> add -> verdict -> compare | e2e (Playwright, new viewport fixture) | `pytest tests/test_frontend_e2e.py -k mobile -x` | Extend existing (web-dev owned) |
| WEB-05 | Footer links to About/Privacy with required disclosures | e2e (text assertions) | `pytest tests/test_frontend_e2e.py -k footer -x` | Extend existing |
| FIT-01 | Missing-data rule -> unverified, names part+spec | unit, one per rule in `RULES` | `pytest tests/test_compatibility_rules.py -x` | Extend existing (web-dev owned) |
| FIT-02 | Exactly 3 verdict states; "All checks passed" never shown while unverified | unit + e2e | `pytest tests/test_compatibility_rules.py tests/test_frontend_e2e.py -x` | Extend existing |
| FIT-03 | Default TDP used -> part named, estimate flagged | unit | `pytest tests/test_compatibility_rules.py -x` | Extend existing |
| SEO-01 | Title/meta/OG/favicon/canonical present; `robots.txt`/`sitemap.xml` 200 | unit (fetch `/`, `/robots.txt`, `/sitemap.xml`) | `pytest tests/test_seo_basics.py -x` | Wave 0 - new file |
| OPS-05 | Per-store staleness names the store | unit (pure function, no DB) | `pytest tests/test_price_freshness.py -x` | Extend existing (data-engineer owned) |
| OPS-06 | 0 extractions + backlog>0 -> loud failure | unit (pure function, no DB) | `pytest tests/test_price_freshness.py -x` or a new `test_extraction_progress.py` | Extend existing or new (data-engineer owned) |
| OPS-07 | `measure_db_growth.py` runs read-only, prints size/growth | manual-only (read-only script, run once and inspect output) - not a hard requirement to unit-test the SQL itself | `python scripts/measure_db_growth.py` | Wave 0 - new file |
| AI-01 | `benchmark_provider.py` scores 8/8 for mistral and google; writes nothing to DB | unit (offline scoring logic) + manual (live provider call, 2 providers) | `pytest tests/test_benchmark_provider.py -x`; `python scripts/benchmark_provider.py --provider mistral`, `--provider google` | Wave 0 - new files |

### Sampling Rate
- **Per task commit:** `python -m pytest -q tests --ignore=tests/test_frontend_e2e.py` (fast, seconds)
- **Per wave merge:** full suite including Playwright (`python -m pytest -q tests`, ~6 min)
- **Phase gate:** full suite green, plus a manual run of `scripts/benchmark_provider.py` against
  mistral and google (Success Criterion #5 names these two providers specifically)

### Wave 0 Gaps
- [ ] `tests/test_cors.py` - covers SEC-01
- [ ] `tests/test_settings.py` - covers SEC-02
- [ ] `tests/test_rate_limits.py` - covers SEC-03
- [ ] `tests/test_security_headers.py` - covers SEC-05
- [ ] `tests/test_docs_disabled.py` - covers SEC-06
- [ ] `tests/test_builder_validation.py` - covers SEC-07 (new test file; note the unknown-ids
      rejection path is already implemented in `builder.py:249-252` and just needs a test)
- [ ] `tests/test_env_example.py` - covers SEC-08
- [ ] `tests/test_error_pages.py` - covers WEB-01, WEB-02
- [ ] `tests/test_seo_basics.py` - covers SEO-01
- [ ] `tests/test_benchmark_provider.py` - covers AI-01's offline scoring path
- [ ] `scripts/measure_db_growth.py`, `scripts/benchmark_provider.py` - the scripts themselves don't
      exist yet
- [ ] Framework install: `pip install slowapi` (flagged `[SUS]` - see Package Legitimacy Audit)

## Security Domain

### Applicable ASVS Categories (Level 1)

| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V2 Authentication | No | No auth surface is introduced this phase (agent tokens are Phase 2, AGENT-04) |
| V3 Session Management | No | No sessions/cookies exist or are introduced; share tokens are opaque URL-path identifiers (`secrets.token_urlsafe(16)`, `builder.py:259` [VERIFIED]), not session state |
| V4 Access Control | Minimal | `/docs`/`/redoc`/`/openapi.json` gating by environment is the only access-control-shaped change (SEC-06) |
| V5 Input Validation | Yes | Pydantic models already used throughout (`SaveBuildRequest`, `CandidateRequest`); SEC-07 adds explicit bounds (count, body size) on top of Pydantic's type validation |
| V6 Cryptography | No material change | `secrets.token_urlsafe` already used correctly for share tokens; nothing new this phase |
| V7 Error Handling and Logging | Yes | WEB-02's no-traceback guarantee; SEC-02's no-credential-in-source guarantee |
| V9 Communications | Partial | CSP/security headers are this app's part; TLS/HSTS is explicitly the Phase-3 proxy's job (see Pitfall 2) |
| V13 API and Web Service | Yes | CORS (SEC-01), rate limiting (SEC-03), hidden docs (SEC-06) are all squarely V13 controls |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| CORS `allow_origins=["*"]` + `allow_credentials=True` | Information Disclosure / Tampering | Explicit origin allow-list, `allow_credentials=False` (SEC-01) |
| Default DB credential committed to source | Information Disclosure | Remove default, fail closed if unset (SEC-02) |
| Unbounded requests to any endpoint (esp. image proxy) | Denial of Service | Per-route rate limiting via `slowapi` (SEC-03) |
| Stack trace / framework version leakage on 500 | Information Disclosure | Already mostly mitigated by Starlette's `debug=False` default; add a branded handler + test (WEB-02) |
| Public OpenAPI schema revealing internal routes/shapes in production | Information Disclosure | Environment-gated docs (SEC-06) |
| Oversized save-build payload (memory/DB pressure) | Denial of Service | Count cap + body-size cap (SEC-07) |
| Spoofable client-IP header used for rate-limit keying before the origin is firewalled | Spoofing | Documented, accepted interim risk until Phase 3's OPS-02 (see Pitfall 3) |
| A compatibility check silently reporting "fine" on missing data | Tampering (of trust, not data) - the core "Nothing embarrassing... goes public" risk this whole phase targets | Explicit `"unverified"` state (FIT-01/02) |

## Sources

### Primary (HIGH confidence - verified this session against installed packages, live DB, or git history)
- `src/api/main.py`, `src/configs/settings.py`, `src/api/deps.py`, `src/api/routes/images.py`,
  `src/api/routes/builder.py`, `src/services/compatibility_engine.py`,
  `src/services/compatibility_rules.py`, `src/domain/builder.py`, `src/services/builder_service.py`,
  `src/db/models/category_specs.py`, `src/db/models/price_history.py`, `src/db/models/store.py`,
  `src/static/index.html`, `src/static/app.js`, `dags/scheduled_scraper_dag.py`,
  `scripts/extract_gpu_titles_groq.py`, `src/services/groq_extraction_service.py`,
  `tests/test_price_freshness.py`, `tests/test_compatibility_rules.py`, `tests/test_image_proxy.py`,
  `tests/test_frontend_e2e.py`, `.claude/agents/web-dev.md`, `.claude/agents/data-engineer.md`,
  `docker-compose.yml`, `requirements.txt`, `pyproject.toml` - all read directly, 2026-09-24
- Installed package source: `starlette==1.3.1` (`middleware/errors.py`, `requests.py`, middleware
  directory listing), `fastapi==0.140.0` (`exception_handlers.py`) - read directly, 2026-09-24
- `docker exec pc_builder_postgres psql` read-only queries against the live database - run directly,
  2026-09-24
- `git log`/`git show` across all local branches and the two stale detached worktrees - run
  directly, 2026-09-24
- `pip index versions slowapi`, `pip index versions fastapi` - run directly, 2026-09-24
- `developers.cloudflare.com/fundamentals/reference/http-request-headers` - fetched directly,
  2026-09-24
- `fastapi.tiangolo.com` (docs_url/redoc_url/openapi_url constructor parameters) - fetched directly,
  2026-09-24

### Secondary (MEDIUM confidence - WebSearch results cross-referenced against multiple independent sources)
- slowapi + reverse-proxy IP-spoofing discussion (`medium.com/@amarharolikar/...`, GitHub issues on
  `jameswagner/usaspending-agent`, `slowapi.readthedocs.io`) - consistent across sources, 2026-09-24
- uvicorn `--proxy-headers`/`--forwarded-allow-ips` behavior (`uvicorn.dev/settings`,
  `fastapi.tiangolo.com/advanced/behind-a-proxy`) - 2026-09-24
- FastAPI security-headers middleware pattern (multiple GitHub issues/PRs and blog posts, converging
  on the same `@app.middleware("http")` shape) - 2026-09-24

### Tertiary (LOW confidence - single-source or refuted; kept only as a documented negative finding)
- A web search result asserting `starlette.middleware.body_limit.RequestBodyLimitMiddleware` exists
  - **checked and refuted** this session against the installed package (see Pitfall 4); do not use.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions confirmed against the live PyPI registry this session
- Architecture (FIT-01/02/03, error handling, freshness): HIGH - every claim about current behavior
  is a direct, line-cited read of the source this session, several cross-checked against installed
  package internals
- Rate limiting / Cloudflare header trust: MEDIUM - the mechanism is correct and cross-referenced
  across independent sources, but the exact `slowapi` response shape wasn't verified against
  installed source (package not present in this environment)
- AI-01 benchmark reconstruction: HIGH confidence that the original 8 cases are irrecoverable
  (exhaustive git-history search), MEDIUM confidence in the specific replacement candidates (real,
  verified-to-exist titles, but their answers still need independent sign-off per Pitfall 9)

**Research date:** 2026-09-24
**Valid until:** 30 days for the FastAPI/Starlette-version-specific claims (these move slowly);
7 days for the live-DB baseline numbers in the AI-01/OPS-07 sections (the catalog changes daily via
the scraping DAG)
