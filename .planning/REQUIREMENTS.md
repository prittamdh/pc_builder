# Requirements: PC Builder 2

**Defined:** 2026-09-24
**Core Value:** When we say a build fits, it fits, and every price is real. When we don't know, we say so.

Every requirement below must be verifiable by a test, a script or a URL check. "In-stock
listings" means `products.in_stock = true` and not legacy, which is what shoppers see.
"Agent" means one installed copy of the scrape extension.

## v1 Requirements

### Security (SEC)

- [ ] **SEC-01**: CORS no longer allows `*` with credentials. In production, a request with an unlisted `Origin` gets no `Access-Control-Allow-Origin` header (test).
- [ ] **SEC-02**: The app refuses to start without `DATABASE_URL`, and no credential appears in source (test plus grep for `pc_builder123` returning nothing).
- [ ] **SEC-03**: Per-IP rate limits on the public API. Tighter limits apply to `/api/v1/images`, `/api/v1/builder/*` and build saving. Going over returns 429 with a JSON body (test with a low limit set in test config).
- [ ] **SEC-04**: The image proxy refuses bodies over 5 MB and anything whose content type isn't `image/*`, serving the placeholder instead (tests).
- [ ] **SEC-05**: HTML responses carry `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and a CSP that includes `frame-ancestors 'none'`. The production proxy adds HSTS (header test plus a curl check on production).
- [ ] **SEC-06**: `/docs`, `/redoc` and `/openapi.json` are off when `ENV=production`. The agent endpoints never appear in any public schema (test).
- [ ] **SEC-07**: Saving a build rejects more than 20 product ids, ids that don't exist, and bodies over 10 KB (tests).
- [ ] **SEC-08**: `.env.example` lists every variable the code reads, with no real values, and a test checks it against `configs/settings.py` and the compose files. On the VM, `.env` is mode 600 and owned by the service user. LLM keys live only there.

### Web (WEB)

- [ ] **WEB-01**: Unknown page paths return a branded 404 page. Unknown `/api/*` paths return JSON 404 (tests).
- [ ] **WEB-02**: Unhandled errors return a generic 500 page or JSON with no traceback or framework details (test that raises inside a route).
- [ ] **WEB-03**: The full Playwright suite, including `test_no_console_errors_on_load`, passes before every deploy. If the suite is skipped (browser missing), the deploy check fails.
- [ ] **WEB-04**: At 375px width a user can search, open the picker, add a part, read the build verdict and open compare. An e2e test covers this flow at 375px.
- [ ] **WEB-05**: The footer links to About/Disclaimer and Privacy pages. They say prices are collected automatically and may lag, that we are not affiliated with any retailer, that shoppers should verify before buying, and they give a contact address for retailers.
- [ ] **WEB-06**: Static assets are served compressed with long cache lifetimes and versioned URLs. `/api/v1/products/models` page 1 has a p95 under 500 ms on production, measured by a script sending 50 requests.

### Scrape agents (AGENT)

- [ ] **AGENT-01**: A job queue table holds scrape jobs (store, URL, allowed headers, job type `category_page` or `product_page`, page number, status, attempts, lease id, lease expiry, agent id). A lease hands out jobs with `SELECT ... FOR UPDATE SKIP LOCKED`. A test with 2 concurrent leasers never assigns the same job twice.
- [ ] **AGENT-02**: A lease expires after 120 s. A reaper returns expired jobs to the queue with backoff. After 3 failed attempts a job is marked `failed` and counted in health (tests).
- [ ] **AGENT-03**: Result upload is idempotent. Re-posting the same `(job_id, lease_id)` returns the first outcome without saving twice. A post with a stale or wrong lease id gets 409 and saves nothing (tests).
- [ ] **AGENT-04**: The owner creates per-install tokens with a CLI (`scripts/agent_tokens.py create|list|revoke`). Tokens are shown once and stored hashed. A revoked token gets 401 on its next request. Agent endpoints return 401 without a valid token and are rate-limited per token (tests).
- [ ] **AGENT-05**: A per-store minimum interval between fetches is stored on `stores` and enforced when leasing, across all agents together. A test with 3 agents never leases two jobs for one store closer together than the interval.
- [ ] **AGENT-06**: Every upload is validated before parsing: body at most 5 MB, the final URL's host equals the job's store host, the content type matches what the platform expects (JSON vs HTML), and challenge/login/captcha pages are detected and marked `blocked`. A category page 1 that parses to 0 products is marked failed, not "empty". Prices must pass `has_usable_price` and the physical bounds. Each rejection is stored with its reason (tests with fixture bodies).
- [ ] **AGENT-07**: The fetch/parse split. A request planner turns (store, endpoint, page) into (url, headers) for every platform `GenericScraper` supports today, and the existing parsers run unchanged on uploaded bodies. Pagination is driven by the server: page N+1 is queued only if page N produced new product ids. The current parser tests still pass, and a planner test covers each platform.
- [ ] **AGENT-08**: Retailer product-page fetches (`repair_unseen_products`, the price repair path) go through `product_page` jobs. No script on the server fetches retailer pages directly, checked by grep plus a test that the server HTTP client refuses store hosts in production mode.
- [ ] **AGENT-09**: Every saved price records the agent and job that fetched it, so one agent's data can be found and removed after a revoke (test).
- [ ] **AGENT-10**: The Chrome extension (Manifest V3, installed unpacked):
  - an options page takes the server URL and token;
  - a `chrome.alarms` alarm polls once a minute, leases a small batch and processes it within the wake;
  - fetches use `credentials: 'omit'`, `cache: 'no-store'` and `redirect: 'follow'`;
  - it refuses any job whose host isn't in its manifest `host_permissions`;
  - it honours each job's `not_before`;
  - it posts results and shows its status on its badge (ok / no token / errors).
  An unpacked-install guide is in `extension/README.md`.
- [ ] **AGENT-11**: A worker process replaces Airflow in production. On a schedule it queues due targets, processes uploads, runs identity and spec extraction and catalog policy, and runs the freshness checks. It calls the existing task functions, and records every run (task, start, end, status, counts, error) in a `pipeline_runs` table (tests).
- [ ] **AGENT-12**: `/health/pipeline` returns 503 when no agent has checked in for 24 h, no price has been saved for 24 h, or any scheduled task's latest run failed or is overdue by more than 2 intervals (tests). The uptime monitor watches it.

### Honest fit (FIT)

- [ ] **FIT-01**: When both slots of a rule are selected but either value is missing, the engine returns an `unverified` item naming the part and the missing spec. Unit tests cover every rule in `RULES`.
- [ ] **FIT-02**: The build verdict has exactly three states: "Problems found" / "No problems found - N checks unverified" / "All checks passed". "All checks passed" never shows while anything is unverified (unit test plus e2e).
- [ ] **FIT-03**: When the wattage estimate uses a typical TDP because a part's TDP is unknown, the response and the UI name that part and say the figure is an estimate (test).
- [ ] **FIT-04**: When both values are known, a passing clearance check shows both numbers and the margin, e.g. "GPU 336 mm, case allows 360 mm, 24 mm spare" (test).
- [ ] **FIT-05**: The case and cooler pickers mark each model "fit data: published / not published / not checked yet". An optional toggle shows only models with published data (e2e).
- [ ] **FIT-06**: Every clearance, height, radiator and socket value shown in the builder or on a model page can be expanded to show its source URL, the verbatim quote and the date read (e2e on a known model).

### Fit data depth (DATA)

- [ ] **DATA-01**: A provenance table stores, for every page-read spec value, the model, field, value, source URL, source kind (manufacturer / retailer / dataset / title), verbatim quote and date. Existing sources are moved out of `cabinet_specs.notes` / `cooler_specs.notes`. A check script finds 0 page-read values without a provenance row.
- [ ] **DATA-02**: A manufacturer-page reader for cabinets fills GPU clearance, cooler height and radiator sizes. It finds the maker's page from the brand's sitemap. It accepts a page only if the model's identifying tokens appear in its title or heading, including variant tokens (V2, Mini, year). It uses the same `is_grounded` and `is_radiator_conditional` rules. Retailer pages are fetched through agent jobs; manufacturer pages may be fetched by the server at a polite rate. Tested offline on saved pages.
- [ ] **DATA-03**: The same reader fills air-cooler `height_mm` and cooler `supported_sockets`, with sockets normalised to the names CPUs use (`LGA1700`, `AM5`, ...). Tested offline, including the `115x` style.
- [ ] **DATA-04**: When the manufacturer page links a spec PDF with a text layer, the reader reads it under the same grounding rules. Image-only PDFs are skipped, with no OCR guessing (test with a fixture PDF).
- [ ] **DATA-05**: If manufacturer and retailer values disagree by more than 10%, the manufacturer value is used, both sources are kept in provenance, and the conflict is logged. Rows marked "Web-verified" are never overwritten (tests).
- [ ] **DATA-06**: A coverage report script prints, per fit field, the % of in-stock listings with a value, broken down by brand, and the count marked "no published source". It is run and recorded at the end of each data phase.
- [ ] **DATA-07**: Models whose pages were checked and state nothing are marked "no published source (checked YYYY-MM-DD)". Models not yet checked stay distinguishable from them (feeds FIT-05).

### Search visibility (SEO)

- [ ] **SEO-01**: The home page has a unique title, a meta description, Open Graph tags, a favicon and a canonical link. `/robots.txt` and `/sitemap.xml` return 200 (tests).
- [ ] **SEO-02**: Each canonical model has a server-rendered page at a stable slug URL. It shows the name, spec table, every offer (store, price, stock, last seen), a price-history summary and the spec sources. The HTML carries the content without JavaScript (test fetches the HTML and asserts on it).
- [ ] **SEO-03**: Model pages include JSON-LD `Product` with `AggregateOffer` (INR `lowPrice`, `highPrice`, `offerCount`), validated against the schema in a test.
- [ ] **SEO-04**: `sitemap.xml` lists every model page with an in-stock offer and is regenerated at least daily.
- [ ] **SEO-05**: A shared build link (`/?build=token`) returns server-rendered title and OG tags (build total, part count) for link previews (test).
- [ ] **SEO-06**: Catalog cards, compare and builder parts link to their model page (e2e).

### Price truth and store reliability (PRICE)

- [ ] **PRICE-01**: Each model shows its lowest current price, its lowest price across all stores in the last 90 days, and how far the current best is above that floor (test on fixture history).
- [ ] **PRICE-02**: A listing whose MRP is more than 10% above the highest price actually observed at any store in the last 90 days gets a "MRP never charged" badge, with the evidence visible (test).
- [ ] **PRICE-03**: A store reliability page shows, per store: last successful fetch, % of listings with price, image and specs, how often in-stock status flips, how often prices change, and the median days a listing stays in stock, each with its sample size (test on fixture data).
- [ ] **PRICE-04**: Every offer shows "seen in stock X ago" (e2e).

### Identity quality (IDEN)

- [ ] **IDEN-01**: A merge audit (groups with more than one distinct model token, or an outlier price spread) and a split audit (near-duplicate keys, prefix pairs) run weekly in the worker. The run fails when either count rises above the last accepted baseline.
- [ ] **IDEN-02**: The 62 cooler/storage prefix-pair splits (e.g. `masterliquid_core_lcd` vs `_lcd_360`) are resolved by re-extraction, not a mechanical merge. The split audit shows the count before and after.

### Operations (OPS)

- [ ] **OPS-01**: Production is one Oracle Always Free Ampere A1 VM in the owner's Indian home region, running Caddy, the API, the worker and Postgres under Docker Compose with arm64 images. One deploy command pulls, runs `alembic upgrade head`, restarts, and smoke-tests `/health`. The runbook is in `docs/DEPLOY.md`.
- [ ] **OPS-02**: The OCI security list and the host firewall allow 443 (and 80) only from Cloudflare's IP ranges, plus SSH (key-only, password login off). Postgres listens only inside Docker, and admin access is by SSH tunnel. Checked with an external port scan and a direct-to-origin request that must fail.
- [ ] **OPS-03**: Nightly `pg_dump` goes to OCI Object Storage (Always Free) and, weekly at least, to a copy off Oracle (Cloudflare R2 free tier). Retention is sized to stay within both free tiers. The job fails loudly if a dump is missing or under 50% of the previous one's size. A restore into a scratch database is done and timed before launch.
- [ ] **OPS-04**: `/health` returns 503 when the database is unreachable, and `/health/freshness` returns 503 when the newest saved price is more than 24 h old. An external uptime monitor (UptimeRobot free) checks `/health`, `/health/freshness` and `/health/pipeline` every 5 minutes and emails the owner.
- [ ] **OPS-05**: A check fails, naming the store, when any active store has saved no price in 24 hours (test).
- [ ] **OPS-06**: The extraction stage fails when a whole cycle made 0 extractions while the backlog was above 0 (every provider exhausted) (test).
- [ ] **OPS-07**: Database size and `price_history` growth per day are measured. Retention (90 days raw, then a daily low/high) keeps 12 months of growth within the block volume and the backups within the free object-storage tiers.
- [ ] **OPS-08**: API and worker logs on the VM are rotated and kept for 14 days. Unhandled API errors go to Sentry's free tier.
- [ ] **OPS-09**: A rebuild drill brings up the whole stack on a fresh VM from the off-Oracle backup and the git repo, following `docs/DEPLOY.md`, before launch. The time taken is recorded. This is the answer to account termination or instance reclaim.
- [ ] **OPS-10**: The OCI tenancy has a budget alert at ₹1. A script lists every OCI resource and flags any that isn't Always Free eligible. It runs at launch and monthly.

### Local AI (AI)

- [ ] **AI-01**: The fixed 8-case PSU benchmark is committed as `scripts/benchmark_provider.py` (titles, expected answers, scoring). It runs against any `(name, url, model, key)` provider and prints the score out of 8, titles/min and JSON-failure count. It writes nothing to the database.
- [ ] **AI-02**: The trial records whether `gpt-oss-20b` runs on the RX 9060 XT's GPU (Ollama ROCm, then Ollama Vulkan, then LM Studio), with VRAM use, titles/min, benchmark score and errors over a 500-title run.
- [ ] **AI-03**: If AI-02 passes the gate (8/8 and at least 60 titles/min), the desktop joins as a pull-based extraction worker using the same lease protocol as the scrape agents. The server can't reach a home PC and no inbound ports are opened. Tests use a fake worker.

## v2 Requirements (after the v1 phases)

- **BREADTH-01**: Add retailers, starting with TheITDepot (PcPaisa covers 18 to our 10).
- **DATA-08**: RAM module height against air-cooler RAM clearance.
- **DATA-09**: Motherboard M.2 slot count and generation, from manufacturer pages.
- **DATA-10**: GPU length coverage audit and gap-fill from AIB manufacturer pages.
- **DATA-11**: PSU form factor (SFX/ATX) and length against case PSU clearance.
- **AGENT-13**: A cross-agent check: a price moving more than 70% is held and re-fetched by a different agent before saving.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Price alerts, notification channels | Owner's decision 2026-08-17: compete on data depth |
| Per-product star ratings | No source data. Averaging listing ratings would give a false-authority number |
| Discount-% sort | Rewards inflated MRP |
| User accounts | Share tokens are enough |
| Chrome Web Store listing for the extension | Owner's machines only, installed unpacked |
| Headless-browser rendering on the server | No store needs JS rendering (all 10 are plain HTTP today) |
| OCR of image-only spec sheets | Can't give a verbatim quote we can trust |
| LLM recall of specs | Proven wrong (Threadripper sockets, Torrent clearance) |
| Paid hosting | Owner's decision: Oracle Always Free, and only the domain is paid |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEC-01 | Phase 1 | Pending |
| SEC-02 | Phase 1 | Pending |
| SEC-03 | Phase 1 | Pending |
| SEC-04 | Phase 1 | Pending |
| SEC-05 | Phase 1 | Pending |
| SEC-06 | Phase 1 | Pending |
| SEC-07 | Phase 1 | Pending |
| SEC-08 | Phase 1 | Pending |
| WEB-01 | Phase 1 | Pending |
| WEB-02 | Phase 1 | Pending |
| WEB-03 | Phase 1 | Pending |
| WEB-04 | Phase 1 | Pending |
| WEB-05 | Phase 1 | Pending |
| FIT-01 | Phase 1 | Pending |
| FIT-02 | Phase 1 | Pending |
| FIT-03 | Phase 1 | Pending |
| SEO-01 | Phase 1 | Pending |
| OPS-05 | Phase 1 | Pending |
| OPS-06 | Phase 1 | Pending |
| OPS-07 | Phase 1 | Pending |
| AI-01 | Phase 1 | Pending |
| AGENT-01 | Phase 2 | Pending |
| AGENT-02 | Phase 2 | Pending |
| AGENT-03 | Phase 2 | Pending |
| AGENT-04 | Phase 2 | Pending |
| AGENT-05 | Phase 2 | Pending |
| AGENT-06 | Phase 2 | Pending |
| AGENT-07 | Phase 2 | Pending |
| AGENT-08 | Phase 2 | Pending |
| AGENT-09 | Phase 2 | Pending |
| AGENT-10 | Phase 2 | Pending |
| AGENT-11 | Phase 2 | Pending |
| AGENT-12 | Phase 2 | Pending |
| OPS-01 | Phase 3 | Pending |
| OPS-02 | Phase 3 | Pending |
| OPS-03 | Phase 3 | Pending |
| OPS-04 | Phase 3 | Pending |
| OPS-08 | Phase 3 | Pending |
| OPS-09 | Phase 3 | Pending |
| OPS-10 | Phase 3 | Pending |
| WEB-06 | Phase 3 | Pending |
| DATA-01 | Phase 4 | Pending |
| DATA-02 | Phase 4 | Pending |
| DATA-03 | Phase 4 | Pending |
| DATA-04 | Phase 4 | Pending |
| DATA-05 | Phase 4 | Pending |
| DATA-06 | Phase 4 | Pending |
| DATA-07 | Phase 4 | Pending |
| FIT-04 | Phase 4 | Pending |
| FIT-05 | Phase 4 | Pending |
| FIT-06 | Phase 4 | Pending |
| SEO-02 | Phase 5 | Pending |
| SEO-03 | Phase 5 | Pending |
| SEO-04 | Phase 5 | Pending |
| SEO-05 | Phase 5 | Pending |
| SEO-06 | Phase 5 | Pending |
| PRICE-01 | Phase 6 | Pending |
| PRICE-02 | Phase 6 | Pending |
| PRICE-03 | Phase 6 | Pending |
| PRICE-04 | Phase 6 | Pending |
| IDEN-01 | Phase 7 | Pending |
| IDEN-02 | Phase 7 | Pending |
| AI-02 | Phase 8 | Pending |
| AI-03 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 64 total
- Mapped to phases: 64
- Unmapped: 0

---
*Requirements defined: 2026-09-24*
*Last updated: 2026-09-24 after owner review (Oracle hosting, scrape agents, local AI last)*
