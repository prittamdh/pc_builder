# PC Builder 2 (working name)

## What This Is

A price-comparison and PC-building site for India. It collects prices from 10 Indian
PC-parts retailers, groups ~12,000 listings into ~6,000 real products, and checks whether the
parts in a build actually fit and work together (socket, memory type, form factor, GPU length,
cooler height, AIO radiator, PSU wattage). It is for Indian PC builders who want the cheapest
real price and a build that will physically go together.

## Core Value

**When we say a build fits, it fits, and every price is real.** When we don't know, we say
so. Everything else gives way to this.

## Business Context

- **Customer**: Indian DIY PC builders, first-timers to enthusiasts, mostly on mobile.
- **Revenue model**: none at launch. Running cost must stay near zero: free hosting, and only the domain is paid for.
- **Success metric**: share of builds whose fit checks are fully verified (no "unverified"), plus weekly returning visitors.
- **Strategy notes**: `docs/competitive_research.md`. PCPartPicker left India. PcPaisa covers more retailers (18) but has no price-history charts, no store-reliability data and only shallow compatibility checks. That gap is our edge.

## The Edge: Data Depth

We don't compete on the number of retailers or on alerts. We compete on data that is deeper
and more honest than anyone else's:
1. **Fit checks with receipts.** Every clearance or height number links to where it came from (a manufacturer or retailer page and the exact quote).
2. **Honest unknowns.** If a spec isn't published, the site says "unverified". It never shows a green tick it can't back up.
3. **Price truth.** Real price history across all stores. MRP is checked against what was actually charged, never used as the baseline.
4. **Store reliability.** Measured from repeated scrapes: whose "in stock" holds and whose prices move.

## Requirements

### Validated (already built and verified, see PROGRESS.md)

- ✓ Scraper parsers for 10 retailers (Shopify/FleetCart JSON, HTMX, Next.js payload, Magento/Woo/OpenCart HTML), in-stock only, with price history since 2026-07-27
- ✓ LLM identity extraction for 9 categories, grouped into canonical models; the colour, trim and brand-only false merges are fixed
- ✓ Spec tables keyed by `canonical_id`, filled from datasets (GPU, PSU), grounded LLM reading, or zero-cost derivation (RAM, SSD)
- ✓ Compatibility engine: socket, memory type, RAM slots/capacity, form factor, GPU clearance, air-cooler height, AIO radiator (warning), PSU wattage
- ✓ Catalog grouped by model, with hierarchical spec filters, sort, URL state and a mobile filter drawer
- ✓ Builder picker (model first, then store), saved and shareable builds that are re-priced on every load, and price-history charts
- ✓ Image proxy (fixes cross-origin image blocking); `test_no_console_errors_on_load` passes as of 2026-09-24
- ✓ Loud pipeline failures: the scrape task fails if every target fails, and `check_price_freshness` fails after 24h with no saved price

### Active

See `.planning/REQUIREMENTS.md`.

### Out of Scope

- **Price alerts and notification channels** (email, Telegram, WhatsApp, Discord). Owner's decision, 2026-08-17. We compete on data depth. (Uptime emails to the *owner* about the site are operations, not this feature.)
- **Per-product star ratings.** The retailers publish none, and averaging ratings from unverifiable listings would look authoritative without being so (`competitive_research.md` §1).
- **Sorting by "discount %".** It rewards inflated MRPs.
- **User accounts.** Share tokens are enough.
- **Regex or recall-based spec filling.** All extraction is grounded LLM reading with a verbatim quote, or a trusted dataset.
- **A Chrome Web Store listing for the scrape extension.** It is installed unpacked on the owner's own machines only.
- **Paid hosting.** The owner's decision: Oracle Always Free, and the domain is the only spend.

## Context

- Brownfield. Map: `.planning/codebase/*.md` (checked on 2026-09-24; corrections are in STATE.md).
- **Today:** everything runs on the owner's Windows PC (Postgres and Airflow in Docker, FastAPI run by hand, and Python scrapers using `curl_cffi`).
- **Target:** one Oracle Always Free Ampere A1 VM in India runs the site, the database and the pipeline. Page fetching moves to a Chrome extension on the owner's machines, which pulls scrape jobs from the server and posts raw pages back. Parsing, LLM extraction and saving stay on the server.
- LLM providers are all free tier: mistral (`ministral-14b-latest`), google (`gemini-3.1-flash-lite`), groq (`gpt-oss-120b`, too throttled for bulk work) and cerebras (402). The local model on the RX 9060 XT is a low-priority trial.
- Fit-data coverage (live cabinet models): GPU clearance 820/1,404, cooler height 732, radiator sizes 1,017/1,459. Air-cooler height 105/163 models. Cooler socket support is only 21/585 models.
- Scraping stopped silently for 5 weeks in Aug-Sep 2026. Freshness guards are in place now.

## Constraints

- **Grounding**: every extracted value needs a verbatim quote from its source, or it is discarded. The reason: a wrong clearance approves a part that won't fit.
- **Budget**: ₹0 hosting (Oracle Always Free, Cloudflare free, R2/Object Storage free tiers). Only the domain is paid, about ₹1,000 a year.
- **Architecture**: arm64 Linux in production, so every image and wheel must have an arm64 build.
- **Tech stack**: Python, FastAPI, PostgreSQL + Alembic, and plain HTML/CSS/JS with no build step. Jinja2 for server-rendered pages. The extension is plain JS on Manifest V3 with no bundler.
- **LLM cost**: free-tier providers only. Quotas run out, so the pipeline must degrade loudly, not silently.
- **Scraping etiquette and safety**: polite per-store rate limits set by the server. The extension fetches with `credentials: 'omit'`, so the owner's cookies and logins never go to a store.
- **Team**: architect (plans, reviews), data-engineer (pipeline, job queue, parsers, migrations), web-dev (API, extension, frontend, deployment). The owner approves each phase.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Canonical identity by LLM extraction plus a deterministic key | Retailer titles are too inconsistent for string matching | ✓ Good (qualifier fields must never identify on their own) |
| Qualifiers (colour, efficiency, brand-only) can't identify a product | Each one caused a false merge | ✓ Good |
| Datasets before LLM (TechPowerUp-derived GPU data, Cybenetics, the 80 PLUS registry) | Other people's verified data beats re-deriving it | ✓ Good |
| Grounded page reading for clearances, with 2 pages agreeing within 10% | Titles never state clearances; recalled values were wrong | ✓ Good |
| Compare prices to the observed 90-day floor, never to MRP | Indian MRPs are inflated | ✓ Good |
| No price alerts | Owner's call; compete on depth | ✓ Firm |
| **Hosting: Oracle Cloud Always Free, one Ampere A1 VM (4 OCPU / 24 GB) in an Indian region, with Cloudflare free in front** | Owner's decision: budget as close to zero as possible | ✓ Decided 2026-09-24 |
| **Scraping by a Chrome extension on the owner's machines, pulling leased jobs from the server** | Pages come from residential browsers and IPs; the server needs no home PC and no tunnel | ✓ Decided 2026-09-24 |
| **No Airflow in production. A small worker process runs the existing task functions on a schedule and records every run** | `airflow standalone` is a dev mode; a proper Airflow is 3-4 extra services for one 15-minute chain. Run history goes in a table, so failures stay loud | — Pending review after Phase 2 |
| **Tailscale dropped** | Everything server-side lives on one VM; extensions use the public HTTPS API with per-install tokens | ✓ Decided 2026-09-24 |
| An unverified fit check is its own state, never shown as passed | Right now a missing value looks exactly like a pass | ✓ Decided (as recommended) |
| Every page-read spec value stores its source URL and quote in a provenance table | This is the edge, and it makes audits possible | ✓ Decided (as recommended) |
| Local AI trial is low priority and goes last | The owner will set up the desktop when it is free. The benchmark script is committed early anyway | ✓ Decided 2026-09-24 |

---
*Last updated: 2026-09-24 after owner review (Oracle hosting, Chrome-extension scraping, local AI deprioritised)*
