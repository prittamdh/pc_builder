# PC Builder 2 - Progress Tracker

## Overall Phase Status

| Phase | Status | Notes |
| :--- | :---: | :--- |
| **Project Setup** | ✅ | Environment, dependencies, pyproject.toml configured |
| **Database Schema** | ✅ | PostgreSQL tables (`stores`, `products`, `price_history`, `scrape_targets`, 9 spec tables) |
| **Dual-Category Architecture (`category` & `p_category`)** | ✅ | `category` preserves raw store metadata while `p_category` powers production UI & PC Builder |
| **Generic Search Scraper** | ✅ | Selector-based, Shopify API, FleetCart API, HTMX, and Next.js App Router scraping |
| **Search Pipeline (Product + PriceHistory)** | ✅ | Automatically persists scraped search items & price snapshots (100% in-stock filtering) |
| **Multi-Store Scraping** | ✅ | 10 stores seeded & verified (`mdcomputers`, `pcstudio`, `vedant`, `primeabgb`, `elitehubs`, `clarion`, `computechstore`, `tpstech`, `modxcomputers`, `tlggaming`) |
| **Product Page Scraper** | ✅ | JSON-LD & fallback extraction for detailed product pages |
| **sid/pid Refactor** | ✅ | Completely implemented & verified end-to-end |
| **Pagination & Scrape Target Management** | ✅ | Multi-page pagination, target seeding & target execution verified |
| **Airflow Scheduling & Web UI** | ✅ | Airflow 2.9.1 container running live on `http://localhost:8085` |
| **FastAPI Backend** | ✅ | Production-grade REST API server & endpoints (`src/api/`) live on `http://127.0.0.1:8000` |
| **Frontend UI** | ✅ | Glassmorphic dark mode UI live on `http://localhost:8000/` |
| **PC Builder Assembly Tool** | ✅ | Component slots, socket/RAM/TDP compatibility & multi-store optimizer |
| **100% In-Stock Purge & Guard** | ✅ | Prevents new out-of-stock seeding while tracking out-of-stock history for existing items |
| **LLM Canonical Identity Extraction** | 🟡 In Progress | Brand/model identity extracted for 9/9 major categories, all wired to canonical grouping; physical specs and remaining data-quality gaps still open |

---

## LLM-Based Canonical Identity Extraction (Current Focus)

**Goal**: map human-errored, inconsistent scraped titles ("Intel Core Ultra 5 225F...", "INTEL Core Ultra 5 225F Processor...") to a shared real-world product identity, so duplicate listings across the 10 stores collapse into one canonical model instead of being treated as 10 different products.

### Architecture
- **Per-listing identity tables** (`cpu_title_extractions`, `ram_title_extractions`, `monitor_title_extractions`, `gpu_title_extractions`, `storage_title_extractions`, `cooler_title_extractions`, `cabinet_title_extractions`, `psu_title_extractions`, `motherboard_title_extractions`): one row per raw product listing, holding `product_id`, `canonical_id`, extracted brand/model fields, LLM confidence, and raw response — for traceability and re-runs without re-calling the API.
- **`canonical_parts`**: one row per unique real-world product (deduped via a deterministic key built from the extracted identity fields). `products.canonical_id` links every listing to its canonical entry.
- **`products.spec_status`** (`pending` / `extracted` / `needs_review` / `failed`): traceability column so any pipeline can find unprocessed products via a simple `WHERE` filter instead of scanning everything.
- **Physical specs (TDP, cores, clocks, socket, etc.) are deliberately out of scope right now** — `cpu_specs`/`monitor_specs` were extended with the schema for this but left empty; the plan is to source these from an external dataset rather than LLM recall, after an experiment showed the LLM confidently hallucinating wrong specs (e.g. wrong socket/core-count for AMD Threadripper parts) when asked to recall from training knowledge instead of extracting from text.

### Per-category status (as of this update)

| Category | Listings | Unique canonical models | Status |
| :--- | ---: | ---: | :--- |
| CPU | 619 | 137 | ✅ Done (2-stage design proven, then simplified to identity-only per user direction) |
| RAM | 1,235 | 853 | ✅ Done — identity + canonical grouping wired via `scripts/wire_ram_canonical.py` |
| Monitor | 1,388 | 824 | ✅ Done |
| Storage | 1,256 | 803 | ✅ Done |
| Power Supply | 1,010 | 421 | ✅ Done |
| CPU Cooler | 1,409 | 525 | ✅ Done |
| GPU | 1,097 | 473 | ✅ Done |
| Motherboard | 1,752 | 989 | ✅ Done — extended with `socket`/`memory_type`/`form_factor` (1,744 / 1,731 / 1,546 populated respectively; gaps are low-confidence/ambiguous titles) |
| Cabinet | 2,044 | 1,337 | ✅ Done |

~11,800 raw listings condensed to ~6,300 unique canonical models across all 9 categories.

### Compatibility engine — verified against real data (2026-08-16)
With motherboard `socket`/`memory_type` now populated, ran a live end-to-end test of `CompatibilityEngine.validate_build()`:
- AM5/DDR5 motherboard + DDR5 RAM → compatible (no warnings)
- AM5/DDR5 motherboard + **DDR4** RAM → correctly flagged `error`: "RAM Standard Mismatch: selected RAM is DDR4, but Motherboard supports DDR5."
- LGA1700/DDR5 motherboard + DDR5 RAM → compatible

The RAM↔Motherboard `memory_type` rule is confirmed working end-to-end.

### CPU physical specs — two-model cross-verification (2026-08-16)
`cpu_specs` was populated for all 136 unique canonical CPU models (per-model, not per-listing — physical specs are a property of the real SKU) using a two-source cross-check rather than a single LLM's recall: Mistral ran the existing grounded Stage-2 extraction (`scripts/extract_cpu_specs_groq.py`), and Claude independently produced its own assessment for the same 136 models from its own knowledge (`data/cpu_specs_claude.json`), written **before** looking at Mistral's output to keep the two sources genuinely independent. A reconciliation pass then compared every field:
- **647 field-level agreements** → accepted at high confidence.
- **324 fields where only one source had data** → accepted at medium confidence (single-source).
- **10 genuine disagreements** (both sources had data, values conflicted, and Claude's own per-model confidence for that SKU was honestly medium/low too — e.g. the vague "3rd Gen"/"4th Gen"/"8th Gen" canonical entries with no real model number) → left null rather than guessed.
- A separate class of ~35 disagreements where Claude's independent confidence for that model was high were resolved in Claude's favor rather than nulled, since the first reconciliation pass showed Mistral had real, identifiable errors on exactly this kind of field: hallucinated sockets (`sWRX9` isn't a real socket — corrected to `sTR5`), architecture mislabeling that contradicted its own grounding text ("3rd Gen"/"4th Gen" titles labeled "Nehalem"/"Westmere" instead of Ivy Bridge/Haswell), inconsistent `integrated_graphics` flags on K-series Intel CPUs and AM5 Ryzen chips (a real, checkable rule: non-F/non-KF SKUs have an iGPU, all AM5 Ryzen desktop chips have one), and base/boost clock values swapped into the wrong field.

Result verified live end-to-end: AM5 CPU + AM5 board → compatible; AM5 CPU + LGA1851 board → correctly flagged `Socket Mismatch`; LGA1700 CPU + LGA1851 board → correctly flagged; LGA1700 CPU + genuine LGA1700 board → compatible. The CPU↔Motherboard `socket` rule — the single most important PC-builder compatibility check, and the one gap flagged as blocking end-to-end verification all session — now works with real data.

### Third-source web verification (2026-08-16)
Went further than the two-model reconciliation: web-searched live spec sheets/reviews (manufacturer pages, TechSpot, Tom's Hardware, GamersNexus, etc. — TechPowerUp's database blocks automated fetches via Cloudflare, worked around it using the Browser tool instead of giving up on that source) for every SKU that both Mistral and Claude were still uncertain about after reconciliation. This caught something neither AI model could have known on its own: **6 of the "uncertain/possibly-hallucinated" SKUs turned out to be real CPUs released in 2026**, after both models' reliable knowledge — Ryzen 7 7700X3D, Ryzen 7 9850X3D, Ryzen 9 9950X3D2 (a genuinely new "Dual Edition" dual-CCD flagship AMD hadn't shipped before), and Intel's "Arrow Lake Refresh" Core Ultra 5 250K / Ultra 7 270K line. Claude had wrongly dismissed all of these as likely mis-extractions. Also got verified, corrected clock speeds for the full Threadripper 9000/9000WX lineup (8 SKUs), which both AI sources had left null.

Final: socket populated on 131/136 models, TDP on 129/136, confidence breakdown {high: 50, medium: 78, low: 8}. The remaining 8 low-confidence rows are all legitimately unresolvable — 3 are vague canonical entries with no real model number in the source title (can't be searched), and 5 are duplicate/mis-series-extracted entries where the real SKU already has correct data under its proper name elsewhere.

---

## All 9 spec tables re-keyed to `canonical_id` + populated (2026-08-16)

The remaining 7 `*_specs` tables (`gpu`, `motherboard`, `ram`, `psu`, `cabinet`, `cooler`, `ssd`) were still keyed per-listing (`product_id`) and held leftover regex-normalizer output. Migration `5e2b8c4f1a97` re-keys all 7 to `canonical_id` (one row per real-world model, matching the CPU/Monitor pattern), drops the stale rows, and adds the standard LLM-metadata columns (`brand`/`confidence`/`notes`/`llm_model`/`raw_response`/`status`/`error`) via a shared `_SpecsMetadataMixin`. `CompatibilityEngine._resolve_slot()` was updated to join on `canonical_id` for every category.

### Data sourcing — external datasets first, LLM only where nothing better exists

| Table | Models | High-conf | Primary source |
| :--- | ---: | ---: | :--- |
| `cpu_specs` | 136 | 50 | Mistral + Claude cross-verification + web search (above) |
| `monitor_specs` | 826 | 705 | Mistral grounded extraction (specs are stated in monitor titles) |
| `gpu_specs` | 555 | 506 | **Bulk import** from RightNow-GPU-Database (TechPowerUp-derived, 2,578 entries) |
| `psu_specs` | 446 | 332 | **Bulk import** from Cybenetics lab certifications + Mistral for the rest |
| `ram_specs` | 834 | 716 | Derived from `ram_title_extractions` — **zero API calls** |
| `ssd_specs` | 805 | 730 | Derived from `storage_title_extractions` — **zero API calls** |
| `motherboard_specs` | 1,359 | 40 | Mistral grounded extraction (slot counts rarely in titles) |
| `cooler_specs` | 585 | 34 | Mistral grounded extraction (socket lists rarely in titles) |
| `cabinet_specs` | 1,405 | 10 | Mistral grounded extraction (clearances almost never in titles) |

**Using other people's work instead of re-deriving it** turned out to be strictly better wherever a real dataset existed:
- **GPU**: 474/555 models matched directly against a TechPowerUp-derived bulk dataset. GPU memory/TDP/recommended-PSU are *chipset-level* specs shared across AIB variants, so a bulk chipset match is more reliable than asking an LLM to recall each of 555 board variants. This is also the only way we got real `length_mm` data.
- **PSU**: Cybenetics publishes independently lab-tested efficiency certifications. Their table is JS-rendered (curl gets an empty shell), but the browser's network log exposed the underlying `code/performance-in.php` endpoint, which returns all 1,152 rows in one request. Worth noting several PSUs certify *higher* than their own marketing name implies (e.g. "Leadex III **Gold**" tests at Platinum) — retailer titles would have given us the wrong tier.
- **RAM / Storage**: needed no external source *or* LLM call. A RAM kit's identity (DDR5-6000 CL30 32GB 2x16) *is* its spec, already captured in Stage 1 — so `ram_specs`/`ssd_specs` are derived directly from the extraction tables, picking the highest-confidence row per canonical model.

### Bugs found and fixed during this work
- **Crash: LLM emitted the string `"null"` instead of JSON null** → `psycopg.errors.InvalidTextRepresentation: invalid input syntax for type integer: "null"` killed a full 1,359-model motherboard run mid-batch. This was latent in *every* spec script. Fixed with shared `nullify`/`as_int`/`as_float`/`as_str`/`as_bool` coercion helpers in `groq_extraction_service.py`, applied across all 7 spec scripts. Helpers deliberately preserve `0` (a real value) and refuse to coerce booleans into ints.
- **Bad PSU bulk matching (caught in spot-check, 219 rows reverted).** The first Cybenetics import matched on brand + loose model substring and ignored wattage entirely, producing wrong pairings — a 1300W EVGA Platinum matched to a 750W Bronze unit, XPG Pylon 750W matched to the 450W entry. Rewritten to require an exact wattage match plus a real model-string overlap; match count dropped 219 → 33, which is the honest number.
- **Silent skip after cleanup.** Nulling the bad PSU rows' *fields* left the rows in place, so the incremental extractor (which only checks row existence) skipped 186 models. Deleted the empty rows and re-ran.
- **Motherboard form-factor errors (5 rows, corrected).** Chipset suffix is physically authoritative — a B650M/B860M board is microATX regardless of what the listing says. Three retailer titles literally said "ATX" for microATX boards (the LLM copied the title faithfully; the *retailer* was wrong). One truncated title ("...Micr...") was read as ITX when it's microATX — the dangerous direction, since ITX would wrongly pass an ITX-case fit check. One had a spurious "M" appended to the chipset.

### Known issues (documented, not silently ignored)
- **Motherboard canonical key merges ITX/microATX variants** — `motherboard:msi:b850:mpg_edge_ti_wifi` contains both the B850 (ATX, 4 DIMM) *and* the B850**I** (ITX, 2 DIMM). Since specs are keyed per canonical model, the ITX board inherits the ATX board's slot count and form factor. Affects **24 of 1,359** groups (~1.8%) — the 5 targeted form-factor corrections above resolved 3 of the original 27, since those were extraction errors rather than true merges. The remaining 24 are genuine distinct-SKU merges. Needs the canonical key to include form_factor (or preserve the chipset suffix) plus a re-run — spun off as a background task rather than patched over.
- **Cooler socket lists are inconsistently normalized** — 21/585 have socket data, of which 4 use bare forms like `"115x,1200"` that won't string-match `"LGA1151"`, causing false warnings. Low impact (that rule is warning-level, not blocking).
- **Cabinet clearance coverage is 5/1,405 for `max_gpu_length_mm`** — this is the *correct* outcome, not a failure. Those numbers are essentially never in Indian retailer titles, and the prompt explicitly forbids estimating them from case category ("it's a mid-tower so ~350mm"). A fabricated clearance number in a compatibility checker is worse than no number: it would confidently green-light a card that doesn't physically fit. The 5 that did populate come from titles literally stating "VGA Max 250mm".
- **2 thermal-paste products classified as CPU Coolers** (Noctua NT-H1/NT-H2 "AM5 Edition") — same class as the GPU-mistagged-as-CPU issue.

### Compatibility rules verified live against real data
- **GPU ↔ PSU**: RTX 5090 (950W recommended) + 450W PSU → correctly warns; + 550W PSU → correctly warns.
- **GPU ↔ Cabinet**: RTX 5090 (304mm) + case with 250mm clearance → correctly **blocks** with `GPU Clearance Error`; same GPU + Fractal Torrent Compact (445mm) → passes.
- **CPU ↔ Motherboard** and **RAM ↔ Motherboard**: verified earlier (above), still passing.
- **Motherboard ↔ Cabinet**: EATX board in a MATX case → correctly blocks with `Case Fit Error` (only started working once form factors were normalized — see below).

---

## Frontend exercised for the first time (2026-08-16)

Everything above had been verified through SQL and Python only. Driving the actual
page surfaced a set of failures that no backend test could have caught, because in
each case the backend was correct.

**The PC Builder's compatibility checking had never worked in a browser.** `app.js`
posted `product_ids` while the API expects `selected_product_ids`, so every call to
`/builder/validate` returned 422. The response status was never checked, so the
failure was swallowed and the summary sidebar stayed pinned to "Incompatibilities
Detected" for every build, including an empty one. The engine was right the whole
time; nothing it produced ever reached the screen.

**`src/static/index.html` was never in git.** A blanket `*.html` ignore rule, meant
for scraped page fixtures, also matched the app's own UI markup — so a fresh clone
had no frontend at all.

**The component picker was effectively unusable.** It filtered whatever the Catalog
tab happened to have loaded and matched on the raw store category, so opening the
builder and clicking Select showed "No matching components loaded" almost every
time. It now fetches per slot, with a search box (the 7800X3D was previously
unreachable past the first page) and a "Compatible only" toggle.

**A silent data-loss bug, exposed by adding the Monitor slot.** `_resolve_slot`
returned `[]` for any slot without a spec resolver, and `filter_candidates` zipped
that against the candidate list — the zip truncated to zero, discarding every
candidate with no error raised anywhere. The slot simply appeared to have no
products. Covered by `tests/test_compatibility_filtering.py`.

Also: removed the dead "Canonical Match (Test)" tab (a regression from deleting the
experimental subsystem — the nav button survived its API), added the CPU Cooler and
Monitor slots, and versioned the script tag so browsers stop running cached JS.

### Compare now matches on canonical id
Compare was using a name substring search — precisely what the canonical identity
work exists to replace. Retailers title the same part very differently, so it only
found listings that happened to share wording: for the Ryzen 7 7800X3D it returned
**3 offers from one store**, when the canonical group holds **12 across nine stores**
spanning ₹7,800–₹68,075. It now compares the canonical group, sorts cheapest-first,
and reports which method matched.

### Supported-platform policy (`src/matching/legacy_policy.py`, 26 tests)
Set by the project owner: Intel Core 10th gen and newer (Core Ultra always current),
AMD Ryzen 3000 and newer, motherboards limited to sockets that can host such a CPU,
memory DDR4 and newer. Products carry an `is_legacy` flag rather than being deleted,
so price history stays intact; they're hidden from both the catalog and the builder.

Intel generation parsing is width-sensitive because Intel encodes it inconsistently
(`9350KF` is 9th gen, `10105` is 10th), and listings that spell it out — "Core i7 8th
Gen", "3rd Gen 4 Cores" — are read from the words, since they previously parsed to a
bare leading digit and slipped through. Anything genuinely unidentifiable stays
visible: hiding a part we merely failed to classify would quietly shrink the catalog,
the worse error.

GPUs are deliberately **not** age-filtered — a GT 710 works in any modern board, so
compatibility already governs whether it belongs in a build.

### Catalog data-quality fixes (survey-driven, 2026-08-16)
A survey of storage/PSU/cabinet/cooler found three problems, none about age:
- **Cabinet form factors** were stored in ten spellings ("E-ATX" vs "EATX", "mATX" vs
  "Micro ATX") and sometimes held a chassis *size* ("Mid Tower", "SFF"). The case-fit
  rule compares strings, so it was silently dead. 752 normalized to ITX/MATX/ATX/EATX,
  13 recovered from titles, 35 cleared — a mid-tower label says nothing about which
  board fits, and assuming ATX would be wrong for a micro-ATX-only chassis.
- **4 coolers support only retired sockets** and can't mount on anything buildable;
  2 more named no socket at all ("Intel/AMD") and were cleared.
- **276 external USB drives** were offered as a build's internal drive. Interface
  alone was insufficient — a portable SSD is often an NVMe drive in a USB enclosure,
  so `interface = "NVMe"` is honest while still being external — so titles are matched
  too. Verified no internal drive was caught.

### Saved & shareable builds (2026-08-16)
An assembled build lived only in page memory and was lost on refresh, so there was no
way to keep one or send it to anyone. `saved_builds` stores the slot->product mapping
under an unguessable share token (`secrets.token_urlsafe`, so a link can't be walked to
reach someone else's build the way a sequential id could).

Selections are stored as **product ids, not a price snapshot**: the ten stores reprice
constantly and the point of the tool is the current best price, so a saved build is
re-validated and re-costed on every load. Stock and compatibility can drift between save
and load, so the stored verdict is never trusted - the response reports components that
went out of stock and flags when the compatibility verdict differs from save time, rather
than quietly showing a different answer.

### Wired into the live scraping DAG (2026-08-16)
Extraction was previously run only via manual one-off script invocations. `dags/scheduled_scraper_dag.py` now has a second task, `extract_canonical_identities`, chained after `process_due_targets`, which calls each category's already-incremental extractor (`reprocess_all=False` default → only products missing `canonical_id`) with a small per-category limit (15) every 15-minute cycle — comfortably under Mistral's free-tier 50 RPM. New products scraped by the DAG now get canonical identity extraction automatically; no more manual script runs needed for steady-state operation. Verified by nulling a real product's `canonical_id` and confirming `airflow tasks test` re-extracted it correctly inside the actual container (not just a clean import).

This replaced the old `normalize_catalog_specs` task, which was broken: it called the legacy regex `NormalizationService` on any `spec_status='pending'` product, but `CPUSpecs`/`MonitorSpecs` no longer have a `product_id` column (re-keyed to `canonical_id` earlier this session) — every pending CPU/Monitor product would have crashed that task. It also surfaced a live bug in 8 of 9 extraction scripts: `spec_status` was only ever set on low-confidence results, so high/medium-confidence extractions (the vast majority) stayed `'pending'` forever despite having real `canonical_id` data. Fixed all 8 scripts and backfilled ~7,300 already-extracted products to the correct `spec_status`.

Also had to pass the Mistral/Groq/etc. API keys into the Airflow container (`docker-compose.yml` didn't expose them before) via `env_file: .env` on the `airflow-standalone` service, and fix `sys.stdout.reconfigure(...)` crashing under Airflow's log-redaction stdout wrapper (`RedactedIO` has no `reconfigure` method) across all 13 extraction/utility scripts.

**Also rotated docker-compose credentials**: `docker-compose.yml` is git-tracked and had `POSTGRES_PASSWORD`, the Airflow Fernet key, the Airflow webserver secret key, and the pgAdmin password hardcoded as literal values. Moved all four into `.env` (gitignored) and switched `docker-compose.yml` to `${VAR}` substitution; generated fresh random values for all four and applied them to the live containers (`ALTER USER` for Postgres since the data volume was already initialized; recreated containers for the rest). Note: pgAdmin's own web-login password only takes effect on a fresh volume init, so its already-initialized login may still need changing manually via pgAdmin's UI.

### Infrastructure built along the way
- `GroqExtractionService` (`src/services/groq_extraction_service.py`): provider-agnostic OpenAI-compatible LLM client (works with Groq or Mistral by swapping `api_url`/`model`/`api_key`), batched extraction with strict index validation (rejects/bisects misaligned batch responses instead of risking a result landing on the wrong product).
- **Switched primary provider from Groq to Mistral** after Groq's free-tier `llama-3.1-8b-instant` proved unreliable in practice (undocumented punitive rate-limit cooldowns far worse than its published 6,000 TPM limit). Mistral's free tier (50,000 TPM / 50 RPM) has run cleanly since. Also obtained Cerebras/Google/NVIDIA keys as further backups (Cerebras currently blocked on account verification).
- Fixed a **canonical-key collision bug**: when extraction failed, all identity fields defaulted to empty/"Unknown" simultaneously, causing genuinely different products to hash to the same canonical key and get silently merged (worst case: 71 unrelated GPUs, PSUs, and coolers merged into one fake "gpu:unknown" bucket). Fixed via `disambiguate_failed_key()` — salts the key with the product's own id when there's no real signal to key off. Repaired already-corrupted data with `scripts/fix_canonical_collisions.py`.

### Bugs found and fixed in the existing pipeline while doing this work
- `NormalizationService.normalize_all_unclassified()` had no `WHERE` filter despite its name — every 15-minute DAG run re-processed the same first ~50 products forever instead of advancing through the catalog. Fixed to filter on `spec_status='pending'`.
- `CategoryClassifier.get_p_category()` accepted a `title` param for smart fallback classification but never used it — any product with an unrecognized raw category silently dumped into "Accessories" regardless of title content. (Not yet fixed — flagged for a future pass.)
- DAG's `is_category` detection compared `target_type` against the wrong enum value (`PRODUCT=2` instead of `CATEGORY=1`), routing ~87% of scrape targets through search-query scraping instead of catalog-page scraping. Fixed.
- Removed DAG task 2 (`enrich_unscraped_products`) — it only ever successfully enriched 38/11,284 products (0.3% success) and its one output field (`description`) was never read anywhere downstream.
- Fixed several category-leak data bugs (old/pulled-out CPUs buried in "Accessories", a cabinet mistagged as CPU, Sennheiser soundbars mistagged as PSU, etc.).

---

## Detailed Task Breakdown

### Database Infrastructure & `(sid, pid)` Architecture (Fully Live & Verified ✅)
- [x] **Composite Product Identity**: Implemented composite primary/unique key `(sid, pid)` across `products` and `price_history`.
- [x] **Dual Category Schema**: Added `p_category` column to `products` table and created Alembic migration `94ff4e0a9e14`.
- [x] **Component Specification Tables**: 9 normalized specification tables (`cpu_specs`, `gpu_specs`, `motherboard_specs`, `ram_specs`, `ssd_specs`, `psu_specs`, `cabinet_specs`, `cooler_specs`, `monitor_specs`).

### Multi-Store Scraping Engine (10 Major Indian PC Hardware Retailers Live & Verified ✅)
- [x] **MDComputers (`sid = 1`)**: Magento HTML catalog scraping (1,460 in-stock products).
- [x] **PCStudio (`sid = 2`)**: WooCommerce catalog scraping (1,839 in-stock products).
- [x] **Vedant Computers (`sid = 3`)**: OpenCart catalog scraping (588 in-stock products).
- [x] **PrimeABGB (`sid = 4`)**: WooCommerce catalog scraping (841 in-stock products).
- [x] **EliteHubs (`sid = 6`)**: Shopify JSON API multi-page pagination (1,650 in-stock products).
- [x] **Clarion Computers (`sid = 7`)**: FleetCart PWA JSON API multi-page pagination (405 in-stock products).
- [x] **Computech Store (`sid = 8`)**: WooCommerce HTMX multi-page pagination (1,941 in-stock products).
- [x] **TPS Tech (`sid = 9`)**: Shopify JSON API multi-page pagination (1,661 in-stock products).
- [x] **ModxComputers (`sid = 10`)**: Next.js App Router payload extraction with `in_stock=true` (491 in-stock products).
- [x] **TLG Gaming (`sid = 11`)**: OpenCart Journal 3 theme with `fq=1` in-stock filter (148 in-stock products).

### Data Integrity & Granular Classification (Fully Live & Verified ✅)
- [x] **100% In-Stock Guard**: Prevents seeding stale out-of-stock items while preserving price history updates for active catalog items.
- [x] **Production `p_category` Normalization**: Categorized all 11,048 products into 10 canonical production categories (`Processor`, `Motherboard`, `Graphics Card`, `RAM`, `Storage`, `Cabinet`, `Power Supply`, `CPU Cooler`, `Monitor`, `Accessories`).

---

## What's Next

1. ~~Reconcile legacy regex `*_specs` data with LLM extraction~~ — **Resolved 2026-08-16.** `motherboard_specs`/`ram_specs`/`gpu_specs`/`psu_specs`/`cabinet_specs`/`cooler_specs`/`ssd_specs` turned out to be populated by the old regex `NormalizationService` (not empty as previously documented), and `CompatibilityEngine._merge()` was preferring those regex values over the verified LLM extraction whenever both existed. Investigated properly before fixing: an initial raw `IS DISTINCT FROM` count of 341 "disagreeing" motherboards was mostly noise (regex simply had `NULL`, not a real disagreement) — only **6 products** had both sources populated with conflicting sockets, and in all 6 the *regex* value was actually correct (MSI Z890 boards; LLM said LGA1700 instead of LGA1851). Broadening the check to every chipset→socket pairing surfaced 22 total LLM inference errors worth fixing directly: the whole H810 chipset family (14 rows, Intel's 800-series companion chipset, real systematic gap), AMD's 2025 B840 refresh chipset getting confused with Intel's similarly-numbered B860 (3 rows), three isolated Intel 400/500-series-vs-LGA1700 mixups, and one WRX80→sTR5 mixup (should always be sWRX8). Corrected those 22 rows directly in `motherboard_title_extractions`, then flipped `CompatibilityEngine._merge()`'s priority so `*_title_extractions` (LLM, now more reliable) wins over `*_specs` (uncontrolled regex leftovers) — the right general default until `*_specs` is repopulated from a real external dataset, at which point that priority should flip back (noted in the code). Re-verified the RAM DDR4/DDR5 mismatch tests still pass and confirmed the fixed Z890 board now resolves to `LGA1851` end-to-end through the engine.
2. **Brand-recognition gaps** — regional/lesser-known brands (EVM, ZION, GEONIX, Dawg, Coconut, Prolab Design, Circle, TAG Gamerz, etc.) are inconsistently recognized, causing some real distinct products to share a coarse "brand unknown, same specs" grouping. Options: add a known-brands hint list to the prompts, or accept as a standing limitation (currently correctly flagged `NEEDS_REVIEW`, not silently wrong).
3. ~~Physical specs sourcing~~ — **Resolved 2026-08-16.** All 9 spec tables are now keyed by `canonical_id` and populated (6,951 model rows total). See the section above for per-table sourcing and coverage.
4. **Motherboard canonical key merges ITX/microATX variants** — 24 groups (~1.8%) merge physically different boards (B850 ATX vs B850I ITX) under one canonical_id, so the compact variant inherits the full-size board's slot count and case requirements. Spun off as a background task 2026-08-16.
5. **GPU listings mistagged as CPU category** — ~78 products with `p_category='CPU'` are actually graphics cards (e.g. "AMD Radeon Pro W7700... Graphics Card"), a `CategoryClassifier` leak found while spot-checking the DAG wiring. Flagged as a separate background task (spawned 2026-08-16) rather than fixed inline. The 2 thermal-paste-as-cooler products are the same class of issue.
6. **Cabinet clearance data needs a non-LLM source** — `max_gpu_length_mm` is populated for only 5/1,405 models because those numbers aren't in retailer titles and must not be guessed. This is the one remaining spec gap where an external dataset (or scraping manufacturer product pages) would add real value, and it directly limits how often the GPU-clearance rule can fire.
7. **`CategoryClassifier.get_p_category()` title fallback** — currently a dead parameter; unrecognized raw categories silently dump into "Accessories" regardless of title content. Worth fixing once more scrape-source categories are seen in practice.
8. **Wire the new Stage-2 spec extractors into the DAG** — `extract_canonical_identities` currently runs only the Stage-1 identity extractors. The 7 new `*_specs` scripts (plus the two zero-API `populate_*_from_extractions.py` scripts) should run after it so newly-scraped models get physical specs automatically. `scripts/classify_legacy_products.py` and `scripts/fix_catalog_data_quality.py` are both idempotent and belong in the same task, otherwise newly-scraped legacy or external parts reappear in the builder.
9. **Frontend surfaces still untested** — Compare, History and the Stores tab were exercised and work, but nothing has been checked on a narrow viewport, and there are no automated frontend tests at all. Every frontend bug found on 2026-08-16 was silent (a swallowed 422, an empty list, a `zip()` truncation), so the absence of errors in the console is not evidence the UI is behaving.
10. **PSU efficiency — official registry imported 2026-08-16, 72 still missing.** The CLEAResult/80 PLUS export (14,371 certified units, `data/raw/All_certified_psus.xlsx`, imported by `scripts/import_80plus_efficiency.py`) closed 5 of the 77 gaps. The remainder are genuinely absent from the registry rather than badly matched - validated by running the matcher against PSUs that already had Cybenetics ratings, where it matched 129/446 and **agreed with Cybenetics on 99 of 124**. Most of the rest are Ant Esports (18), an Indian rebrand whose certification is held by the ODM under a different manufacturer name, so only the vendor's own page carries the rating.

    The 25 disagreements are not import errors - they surface a **PSU canonical key that is too coarse**. ASUS sells "TUF Gaming 750W" in both Bronze (`TUF-GAMING-750B`) and Gold (`TUF-GAMING-750G`) trims, and Antec's HCG750 likewise, but the key is only brand+model+wattage, so both variants collapse into one canonical model and inherit whichever rating was written last. Same class of defect as the B850/B850I motherboard merge. The importer therefore only fills gaps and never overwrites an existing rating. Fixing it means adding the efficiency trim to the PSU canonical key and re-running identity extraction.
