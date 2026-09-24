# Roadmap: PC Builder 2

## Overview

Make the site safe (Phase 1), move page fetching to Chrome extensions on the owner's
machines (Phase 2), then go live on Oracle Always Free for ₹0 hosting (Phase 3). After launch,
build the lead in data depth: fit checks with sources, pages Google can index, honest price
and store data, and cleaner product grouping. The local AI trial goes last and is
optional. Price alerts are out of scope by the owner's decision.

**Why the extension comes before go-live, not inside it:** the site can't launch without
fresh prices, and with the owner's PC out of the picture the extension is the only planned
fetch path. Keeping it as its own phase gives a clean test gate: extensions on 2+ machines
keep all 10 stores fresh for 48 h against a local server *before* anything is public. Oracle
signup and VM setup don't wait for it. They start on day one, because ARM capacity can take
days to get.

## Phases

- [ ] **Phase 1: Launch hardening** - Security, error pages, honest "unverified" fit verdicts, loud per-store failures, commit the benchmark
- [ ] **Phase 2: Scrape agents** - Chrome extension plus a server job queue; the server parses and saves; a worker replaces Airflow
- [ ] **Phase 3: Go live on Oracle Always Free** - ARM VM, Cloudflare, backups on and off Oracle, monitoring, rebuild drill; the site is public at the end
- [ ] **Phase 4: Fit data with receipts** - Close the clearance, height and socket gaps from manufacturer pages; every value cites its source
- [ ] **Phase 5: Model pages and search visibility** - A server-rendered page per product, structured data, sitemap
- [ ] **Phase 6: Price truth and store reliability** - 90-day floors, the "MRP never charged" check, a store reliability page
- [ ] **Phase 7: Identity quality** - Weekly merge/split audits that fail loudly; fix the known false splits
- [ ] **Phase 8: Local AI trial (low priority)** - When the RX 9060 XT desktop is free; joins as a pull-based worker only if it passes

## Parallel Work at a Glance

| When | data-engineer | web-dev | owner + manager |
|------|---------------|---------|-----------------|
| Phase 1 | 01-04 (checks, DB measurement) and 01-06 (benchmark) | 01-01, then 01-02, then 01-03, then 01-05 | Oracle signup, VM, domain (03-01), started now; approve the slowapi package (01-05) |
| Phase 2 | 02-01 (queue + protocol), then 02-02 (planner/parse split), then 02-03 (worker) | after Phase 1: 02-04 (agent API), then 02-05 (extension) | install the extension on 2+ machines |
| Phase 3 | 03-03 (backups, restore, rebuild drill) | 03-02 (prod stack, health, Caddy) | 03-04 cutover |
| Phase 4 + 5 | 04-01, 04-02, 04-03 | 04-04, then Phase 5 | - |
| Phase 6 | 06-01 | 06-02 (after the 06-01 contract) | - |
| Phase 7 | 07-01, 07-02 | - | - |
| Phase 8 | 08-01, 08-02 (only when the desktop is free) | - | runs the installs |

"Parallel" means the tasks share no files. Within one agent, tasks run one after another.
data-engineer's 02-01..02-03 can start while web-dev is still on Phase 1: they touch only new
queue/pipeline modules, `src/scrapers/`, and migrations.

## Phase Details

### Phase 1: Launch hardening

**Goal**: Nothing embarrassing or unsafe goes public. Fit checks never claim more than we know. Failures are loud, per store.
**Depends on**: Nothing
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04, SEC-05, SEC-06, SEC-07, SEC-08, WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, FIT-01, FIT-02, FIT-03, SEO-01, OPS-05, OPS-06, OPS-07, AI-01
**Owners**: web-dev (01-01, 01-02, 01-03, 01-05), data-engineer (01-04, 01-06)
**Success Criteria** (what must be TRUE):
  1. A build whose case has no GPU-clearance data never shows "All checks passed". It shows "No problems found - 1 check unverified" and names the case and the missing spec.
  2. A request from another site's origin gets no CORS permission. Hammering `/api/v1/images` returns 429. `/docs` is gone in production mode.
  3. A bad URL shows a branded 404. A server error shows no traceback.
  4. A check fails, naming the store, when one store saves nothing for 24h.
  5. `scripts/benchmark_provider.py` reproduces 8/8 for mistral and google.
  6. The full test suite, including all Playwright tests, passes.

**Plans**: 6 plans (the draft 4 were split to keep each plan at 2-3 tasks; existing IDs kept)

Plans:
**Wave 1**
- [ ] 01-01-PLAN.md (web-dev, wave 1): Config and header hardening: explicit CORS, no default DB URL, security headers, docs off in prod, `.env.example` plus its test, and the phase's config inventory (SEC-01, 02, 05, 06, 08)
- [ ] 01-04-PLAN.md (data-engineer, wave 1): Per-store freshness check, loud "0 extractions with a backlog" check, read-only `scripts/measure_db_growth.py` (OPS-05, 06, 07). **Parallel with web-dev.**
- [ ] 01-06-PLAN.md (data-engineer, wave 1): `scripts/benchmark_provider.py` rebuilt from independently verified PSU cases (the originals were never committed), offline test, live mistral/google runs (AI-01). **Parallel with web-dev.**

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 01-02-PLAN.md (web-dev, wave 2): Branded 404/500, SEO basics (head tags, robots.txt, sitemap.xml), About/Privacy pages with a config placeholder for the contact address (WEB-01, 02, 05, SEO-01)

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 01-03-PLAN.md (web-dev, wave 3): Honest fit verdict (`unverified`, three states, named wattage estimate), e2e skip-means-fail guard, 375px flow (FIT-01..03, WEB-03, WEB-04)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 01-05-PLAN.md (web-dev, wave 4): `slowapi` rate limits (after an owner package check), streaming image-proxy cap, save-build caps (SEC-03, 04, 07)

### Phase 2: Scrape agents

**Goal**: Prices stay fresh with no dependency on any one home PC. Chrome extensions on the owner's machines fetch pages; the server hands out work, validates, parses and saves.
**Depends on**: Phase 1 for web-dev's plans. data-engineer's plans can start alongside Phase 1.
**Requirements**: AGENT-01, AGENT-02, AGENT-03, AGENT-04, AGENT-05, AGENT-06, AGENT-07, AGENT-08, AGENT-09, AGENT-10, AGENT-11, AGENT-12
**Owners**: data-engineer (02-01..02-03: queue, parse, worker), web-dev (02-04..02-05: agent API endpoints, extension)
**Success Criteria** (what must be TRUE):
  1. With the extension on 2+ of the owner's machines and the local stack running the worker (no Airflow), all 10 stores save fresh prices for 48 h. The saved price count per store is within 10% of a normal day under the old scraper.
  2. Closing Chrome on one machine mid-job loses nothing: its leases expire and another agent finishes the work. No job is saved twice.
  3. A revoked token is refused on its next call. A request without a token gets 401.
  4. A doctored upload (wrong host, a challenge page, 6 MB, a page 1 with 0 products) is rejected with a stored reason and saves nothing.
  5. With every extension off for 24 h, `/health/pipeline` returns 503.

**Plans**: 5 plans

Plans:
- [ ] 02-01 (data-engineer): Migration for `scrape_jobs`, `scrape_agents` (hashed token, name, last_seen, revoked_at) and `pipeline_runs`; `stores.min_fetch_interval_s`; agent/job ids on `price_history`. Queue service: enqueue, lease (`FOR UPDATE SKIP LOCKED` plus the per-store interval), reaper, idempotent `complete(job_id, lease_id, body)`. `scripts/agent_tokens.py`. Concurrency tests. Publish the JSON contract (below) as `docs/AGENT_PROTOCOL.md`.
- [ ] 02-02 (data-engineer): Split `GenericScraper` into a request planner (url + headers per platform and page) and the unchanged `GenericParser`. Upload validation and challenge detection. Server-driven pagination. The `product_page` job type for `repair_unseen_products`. The server-side retailer fetch is refused in production (kept for tests and local debugging). Files: `src/scrapers/*`, new `src/pipeline/scrape_results.py`, tests. Runs after 02-01.
- [ ] 02-03 (data-engineer): The worker: `src/pipeline/worker.py` runs the existing DAG task functions (`execute_canonical_extraction`, `execute_physical_spec_extraction`, `execute_catalog_policy`, the freshness checks) plus enqueue/reap/parse on a schedule. Each run goes into `pipeline_runs`, and exceptions are recorded and re-raised. A `worker` service in compose. Airflow stays for local dev until Phase 3 has run clean for 7 days, then it is retired.
- [ ] 02-04 (web-dev): Agent endpoints under `/api/agent/` (lease, result, heartbeat) calling 02-01's queue service. Bearer-token auth, per-token rate limits, excluded from the OpenAPI schema. `/health/pipeline`. Starts once `docs/AGENT_PROTOCOL.md` exists; can overlap 02-02.
- [ ] 02-05 (web-dev): The extension in `extension/`: `manifest.json` (MV3; permissions `alarms`, `storage`; `host_permissions` = the 10 store hosts plus the server), a service worker, an options page, badge status, and `extension/README.md` (install unpacked, paste a token). Tested against a local server with fixture jobs. After 02-04.

**Extension and job-queue design**

- **Protocol** (all over HTTPS, JSON, `Authorization: Bearer <agent token>`):
  - `POST /api/agent/lease {max_jobs}` returns `[{job_id, lease_id, url, headers, store_host, not_before}]`. The server picks `queued` jobs whose store is past its minimum interval, locks them with `SKIP LOCKED`, and sets `leased` with a 120 s expiry. A row lock plus a status change means a job can't be handed out twice.
  - `POST /api/agent/result {job_id, lease_id, final_url, status, content_type, body}` is accepted only for the current lease. The same `(job_id, lease_id)` again returns the stored outcome (idempotent). A stale lease gets 409.
  - A reaper puts expired leases back in the queue with backoff; after 3 attempts the job is `failed`. Every lease call also records a heartbeat (`last_seen`).
- **Auth**: the owner runs `agent_tokens.py create --name laptop`. The token is shown once and stored as a SHA-256 hash. `revoke` takes effect on the next request. The endpoints are hidden from the public schema, need a token, and are rate-limited per token. Every saved price records the agent that fetched it, so a leaked or misbehaving agent's data can be traced and removed.
- **Fetch safety**:
  - Fetches use `credentials: 'omit'`, so no cookies or logins go to stores. `cache: 'no-store'`.
  - Only headers from a server-side allowlist are set (`Accept`, `X-Requested-With`, `HX-Request`).
  - The extension refuses any host not in its manifest. So even a compromised server can't make it fetch intranet or arbitrary URLs.
  - Pacing is per store and set centrally, because several agents share one budget. Agents on the same home network share one IP, so intervals must be conservative. A store that blocks that IP blocks the owner's own browsing too.
- **Server trusts the extension less than itself**: size cap, host check on the final URL, content-type check, challenge/login detection, a parse sanity check, and price bounds. Rejections are stored with a reason and counted in health.
- **Fetch vs parse**: today `GenericScraper` builds the URL and headers, does one GET, and calls `GenericParser.parse_search/parse_product` on the text. Only the GET moves to the extension. No store needs JS rendering. EliteHubs and TPS Tech are Shopify `products.json`, Clarion is a FleetCart JSON API, Computech is an HTMX partial behind a header, ModxComputers embeds its Next.js payload in the HTML, and the rest are plain HTML. So plain `fetch()` covers all 10 with no tabs and no offscreen rendering. A real browser also passes the TLS fingerprinting that `curl_cffi` fakes today. Pagination moves to the server, because stopping depends on the parse ("no new product ids").
- **Manifest V3**: the service worker sleeps. A `chrome.alarms` alarm (1-minute period; Chrome's minimum is 30 s) wakes it. Each wake leases a small batch sized to finish within about 25 s of pacing, uploads, and returns. No long-lived loop is needed. If Chrome still cuts batches off, the fallback is an offscreen document running the loop.
- **Who fetches what**: retailer category and product pages go through agents only. Manufacturer pages (Phase 4) and the image proxy stay server-side: they are low volume, and manufacturer sites don't price-scrape-block.

### Phase 3: Go live on Oracle Always Free

**Goal**: The site is public on its own domain over HTTPS at ₹0 hosting, backed up on and off Oracle, watched, and rebuildable elsewhere within hours.
**Depends on**: Phase 2 success criteria met. The owner's Oracle signup and VM (03-01) run from day one of Phase 1.
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04, OPS-08, OPS-09, OPS-10, WEB-06
**Owners**: owner + manager (03-01, 03-04), web-dev (03-02), data-engineer (03-03)
**Success Criteria** (what must be TRUE):
  1. `https://<domain>/` loads on a phone in India through Cloudflare. A direct request to the VM's IP on 443 is refused.
  2. Extensions post to production, and "Last updated" moves within 15 minutes.
  3. Last night's dump is in OCI Object Storage, this week's is in R2, and a timed restore has been done.
  4. A rebuild drill on a fresh VM from the R2 copy has been done and timed.
  5. The OCI budget alert (₹1) is set, and the resource audit shows only Always Free resources.
  6. The uptime monitor is green on `/health`, `/health/freshness` and `/health/pipeline`.

**Plans**: 4 plans

Plans:
- [ ] 03-01 (owner + manager, starts now): OCI signup in the home region, the pay-as-you-go decision (see Decisions), and an Ampere A1 VM (4 OCPU / 24 GB, Ubuntu 24.04 arm64): 50 GB boot volume plus a 150 GB block volume mounted at `/data` for Postgres and Docker volumes. SSH key-only, and the security list set to Cloudflare ranges. Domain bought, with DNS on Cloudflare (proxied) and a Cloudflare Origin CA certificate.
- [ ] 03-02 (web-dev): `Dockerfile` (arm64), `docker-compose.prod.yml` (Caddy, API, worker, Postgres on `/data`), `Caddyfile` (Origin CA cert, HSTS, compression), `scripts/deploy.sh`, `/health` and `/health/freshness`, Sentry hook, log rotation, `docs/DEPLOY.md`. **Parallel with 03-03.**
- [ ] 03-03 (data-engineer): `scripts/backup_db.sh` (nightly to OCI Object Storage; weekly copy to R2; retention sized to 20 GB / 10 GB; size check), a restore test, the rebuild drill script, `scripts/oci_free_audit.py`, and applying the OPS-07 rollup if growth needs it. **Parallel with 03-02.**
- [ ] 03-04 (manager + owner): One-time `pg_dump` from home and restore to the VM. Point the extensions at production. Run the launch checklist (all Phase 1-3 requirements green). Turn the Cloudflare proxy on and announce a soft launch. Stop home Airflow once production has run clean for 7 days.

**Oracle Always Free: setup and gotchas**

| Gotcha | What happens | How we handle it |
|--------|--------------|------------------|
| "Out of host capacity" for A1 | VM creation fails, sometimes for days, in popular regions | Start 03-01 on day one. Retry creation (the OCI CLI in a slow loop is fine). If needed, start at 2 OCPU / 12 GB and resize later. Upgrading to pay-as-you-go usually removes the problem. The home region can't be changed after signup, so pick it deliberately |
| Idle reclaim | Oracle stops Always Free VMs that look idle over 7 days: CPU 95th percentile under 20%, network under 20%, and (for A1) memory under 20%. A light site can meet all three | **Recommended: upgrade the account to pay-as-you-go.** Always Free resources stay free, and PAYG accounts are exempt from idle reclaim. Guard against accidental spend with the ₹1 budget alert and the monthly free-resource audit. Don't burn CPU artificially to look busy |
| Account termination | Free-tier accounts have been closed with little warning | Keep one backup copy **off Oracle** (R2). Keep DNS on Cloudflare so a move is a DNS change. Keep the git repo plus `docs/DEPLOY.md` as the whole setup. The rebuild drill proves recovery. Don't store anything only on Oracle |
| Storage limit | 200 GB total block storage across boot and block volumes. Object Storage is 20 GB free | 50 GB boot plus 150 GB data volume. `price_history` retention (OPS-07). Backup retention sized to the free tiers |
| ARM (aarch64) | Every image and wheel must exist for arm64 | Postgres, Caddy and python-slim images are multi-arch. psycopg binary, lxml and curl_cffi publish aarch64 wheels, and curl_cffi is no longer needed in production anyway. 03-02 builds on arm64 first thing to catch surprises |
| Egress, bandwidth | 10 TB/month out is free | Cloudflare caches static files and proxied images, so it's far below the limit |

**Airflow on ARM, verdict:** it would run (arm64 images exist, and 24 GB is plenty), but it
isn't worth it. `airflow standalone`, which is what runs today, is documented as dev-only. A
proper deployment is a scheduler, webserver, triggerer and metadata database for one
15-minute task chain. A single worker process calling the same task functions, with a
`pipeline_runs` table and `/health/pipeline`, keeps failures loud with far less to break.
Rough memory plan: Postgres 4-6 GB, API 1 GB, worker 1-2 GB, Caddy negligible. That leaves more
than half the VM spare.

**Tailscale:** dropped. Nothing crosses from home to server except the extensions over
HTTPS. Admin database access uses an SSH tunnel.

**Cost:** ₹0 hosting. The domain is about ₹600-1,000 a year for a `.in`. Cloudflare,
UptimeRobot and Sentry are free tiers. R2 is free up to 10 GB but needs a card on file.

### Phase 4: Fit data with receipts

**Goal**: Close most of the clearance, height and socket gaps from primary sources, and show where every number came from.
**Depends on**: Phase 1 (unverified states). Phase 2 (retailer pages come through agent jobs). 04-04 depends on 04-01's contract.
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, FIT-04, FIT-05, FIT-06
**Owners**: data-engineer (04-01..04-03), web-dev (04-04)
**Success Criteria** (what must be TRUE):
  1. Coverage report run and recorded. Targets are goals, not quotas; no value is ever forced to meet them: GPU clearance on at least 85% of in-stock cabinet listings, air-cooler height on at least 85%, cooler socket support on at least 75%. Everything else is marked "no published source" or "not checked yet".
  2. 0 page-read values without a provenance row.
  3. A 30-value random spot check per new source brand against the live manufacturer page finds 0 wrong values before that brand's values are enabled.
  4. In the builder, a user can click a case's GPU clearance and see the manufacturer URL and the exact quote.
  5. The case picker can show only cases with published clearance.

**Plans**: 4 plans

Plans:
- [ ] 04-01 (data-engineer): Provenance table migration and backfill from `notes`. The existing readers (`scrape_cabinet_clearance.py`, `scrape_cooler_height.py`, `scrape_cabinet_radiators.py`, `scrape_psu_efficiency.py`) switch to agent `product_page` jobs and write provenance. Publish the JSON shape for web-dev.
- [ ] 04-02 (data-engineer): Gap audit by brand. Manufacturer-page finder via brand `sitemap.xml` (server-fetched, polite, respects robots.txt) with a strict identity match. Cabinet reader reusing `matching.cabinet_clearance` grounding. The conflict rule. The "no published source" marker. Offline fixture tests.
- [ ] 04-03 (data-engineer): Air-cooler height and `supported_sockets`, socket normalisation, text-layer PDFs. Runs after 04-02 (shared reader). Coverage report at the end.
- [ ] 04-04 (web-dev): Margin display, fit-data markers and filter, expandable source citations. **Parallel with 04-02/04-03** once 04-01's contract is fixed.

### Phase 5: Model pages and search visibility

**Goal**: Every product has a page that Google can index and people can share, showing our data depth.
**Depends on**: Phase 3 (a live domain). Phase 4 is best done first so pages show sources, but it doesn't block.
**Requirements**: SEO-02, SEO-03, SEO-04, SEO-05, SEO-06
**Owner**: web-dev
**Success Criteria** (what must be TRUE):
  1. `curl https://<domain>/p/<slug>` returns HTML containing the product name, spec table, offers and sources, without JavaScript.
  2. Google's Rich Results test accepts the Product and AggregateOffer data on a sample page.
  3. `sitemap.xml` lists every in-stock model and is submitted in Google Search Console.
  4. Pasting a shared build link into WhatsApp shows a preview with the build total.

**Plans**: 2 plans

Plans:
- [ ] 05-01 (web-dev): Jinja2 model page route, stable slugs (with the redirect rule decided up front so a re-key doesn't break old links), JSON-LD, sitemap generator. **Parallel with data-engineer's Phase 4 plans.**
- [ ] 05-02 (web-dev): OG tags for shared builds, and links from cards, compare and builder to model pages.

### Phase 6: Price truth and store reliability

**Goal**: Show things no Indian competitor shows: real price floors, fake-MRP evidence, and which stores' data can be trusted.
**Depends on**: Phase 5
**Requirements**: PRICE-01, PRICE-02, PRICE-03, PRICE-04
**Owners**: data-engineer (06-01), web-dev (06-02)
**Success Criteria** (what must be TRUE):
  1. A model page shows "₹X now, 90-day low ₹Y across all stores, Z% above".
  2. A listing with an MRP that was never charged shows the badge and a link to the evidence chart.
  3. The Stores tab returns, with per-store reliability figures and sample sizes.

**Plans**: 2 plans

Plans:
- [ ] 06-01 (data-engineer): A daily stats job in the worker (per model and per store) writing summary tables, with its migration.
- [ ] 06-02 (web-dev): UI for price stats, the MRP badge and the store reliability page. After 06-01's table shape is agreed.

### Phase 7: Identity quality

**Goal**: False merges and false splits are caught automatically, in both directions, and the known splits are fixed.
**Depends on**: Phase 2 (the worker runs the weekly audits)
**Requirements**: IDEN-01, IDEN-02
**Owner**: data-engineer
**Success Criteria** (what must be TRUE):
  1. A weekly worker task runs both audits and fails when either count rises above the accepted baseline.
  2. The 62 known prefix-pair splits are re-extracted. The split audit shows the before and after counts, and no new merges appear.

**Plans**: 2 plans

Plans:
- [ ] 07-01 (data-engineer): Merge audit plus split audit scripts, a baseline file, and the worker task.
- [ ] 07-02 (data-engineer): Re-extract and re-key the prefix-pair listings. Runs after 07-01.

### Phase 8: Local AI trial (low priority)

**Goal**: Find out whether the RX 9060 XT desktop can take on bulk extraction with no quota limit.
**Depends on**: Nothing in the roadmap. Starts whenever the owner frees the desktop. AI-01 (the benchmark) is already done in Phase 1.
**Requirements**: AI-02, AI-03
**Owner**: data-engineer (the owner runs the installs)
**Success Criteria** (what must be TRUE):
  1. A short written result: the backend that worked (Ollama ROCm, then Ollama Vulkan, then LM Studio), whether it ran on the GPU, VRAM used, titles/min, score out of 8, and errors over 500 titles.
  2. If the gate passes (8/8 and at least 60 titles/min), the desktop leases extraction batches from the server through the same token-and-lease protocol as the scrape agents, with no inbound ports opened. If it fails, the result is recorded and nothing is merged.

**Plans**: 2 plans

Plans:
- [ ] 08-01 (data-engineer + owner): Trial run on the desktop with `benchmark_provider.py`.
- [ ] 08-02 (data-engineer, only if the gate passes): An `extraction` job type on the queue and a small Python pull-worker for the desktop.

## Design Notes

### Closing the fit-data gaps without breaking grounding

About 35% of cabinets lack GPU clearance and about 35% of air coolers lack height, because
retailer pages don't state them. The fix is better *sources*, never estimation:
1. **Manufacturer pages first**, found through the brand's own `sitemap.xml`. No search engine, so no ranking noise.
2. **Identity before numbers.** A page is accepted only if the model's identifying tokens, including variant tokens, appear in its title or heading. The wrong page is the most dangerous failure here, because it gives a real quote for the wrong product.
3. **Same grounding rules as today.** A verbatim quote containing the number, range checks, radiator-conditional limits rejected in code, and 2 sources agreeing within 10%. If they disagree, the manufacturer wins, both sources are kept and the conflict is logged. "Web-verified" rows are untouched.
4. **Spec PDFs** are read only if they have a text layer. No OCR.
5. **Spot-check each new brand** (30 values) before its values can trigger a blocking error.
6. **Honest presentation.** Three fit states, known margins shown with numbers, a clickable source for every number, "published / not published / not checked" markers, and an optional "published only" filter.

## Decisions Needed from Owner

Decided on 2026-09-24 and removed from this list: hosting (Oracle Always Free), where fetching
runs (Chrome extension), Tailscale (dropped), budget (free plus domain), local AI (last,
low priority), and everything else as recommended (retention, API docs off, soft launch, Sentry
free, the local-AI gate).

| # | Decision / action | Recommendation |
|---|-------------------|----------------|
| 1 | **Site name and domain** (blocks Phase 3) | A short `.in` that doesn't clash with PcPaisa, PickPCParts or PartsRadar. About ₹600-1,000 a year |
| 2 | **Oracle signup** (owner only) | **Decided: Mumbai home region.** Owner signs up |
| 3 | **Upgrade the Oracle account to pay-as-you-go** | **Decided 2026-09-24: yes**, with a ₹1 budget alert and a monthly audit |
| 4 | **Off-Oracle backup account**: Cloudflare R2 (free up to 10 GB, card on file) | **Yes, R2.** The fallback with no signup is a weekly pull to the owner's PC, but that depends on the PC being on |
| 5 | **Which machines run the extension** | At least 2, ideally on **different networks** (for example home plus a phone hotspot or a second location). Machines on the same network share one IP and one block risk |
| 6 | **Contact email** for the About page and retailer requests | A dedicated address on the new domain (Cloudflare Email Routing is free) |

## Progress

**Execution Order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Oracle provisioning (03-01) and data-engineer's Phase 2 plans start during Phase 1.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Launch hardening | 0/6 | Planning | - |
| 2. Scrape agents | 0/5 | Not started | - |
| 3. Go live on Oracle Always Free | 0/4 | Not started | - |
| 4. Fit data with receipts | 0/4 | Not started | - |
| 5. Model pages and search visibility | 0/2 | Not started | - |
| 6. Price truth and store reliability | 0/2 | Not started | - |
| 7. Identity quality | 0/2 | Not started | - |
| 8. Local AI trial (low priority) | 0/2 | Not started | - |
