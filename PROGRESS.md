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

### Catalog sorting, and the price bug it exposed (2026-08-17)

Adding sort to the catalog was meant to be a small UI job. It surfaced two data
defects instead, both of which had been invisible precisely because nothing had ever
ordered the catalog by price.

**Computech Store (sid 8) was pricing products from their own titles.**
`_parse_computech_html` ran `₹?\s*(\d{1,3}(?:,\d{3})+|\d{4,6})` over the whole card
text and took the first match above 500. A card's text begins with the product title,
the rupee sign was **optional**, and hardware titles are full of 4-6 digit numbers
that are not prices. So the parser sold model numbers, memory speeds, sockets and
wattages as prices. Measured live against computechstore.in on 2026-08-17:

| Title | Parsed as | Actually |
|---|---|---|
| Colorful iGame GeForce RTX 5080 | ₹5,080 | ₹1,54,499 |
| Colorful iGame RTX 5070 Ti | ₹5,070 | ₹1,24,499 |
| NEXTRON RX 7600 XT | ₹7,600 | ₹34,999 |
| ASRock RX 9050 Challenger | ₹9,050 | ₹30,999 |

An unbiased 500-product sample across the store found **57% carried a price identical
to a number in their own name**. This is the same failure as the PSU-efficiency
carousel bug: an unanchored regex over too much text returning a confident wrong
answer. The fix is to require the rupee sign; on the live page that picks the correct
price in every case checked, and a card with no marked amount is now skipped rather
than assigned an invented one. `tests/test_price_extraction.py` covers it offline.

Severity is worth stating plainly: Computech is the largest store in the catalog, and
systematically understated prices mean it would have won almost every price
comparison the tool made.

**Repaired the same day, in two passes.** A category re-scrape
(`re_scrape_all_stores.py`, now takes an optional store argument) walked the store's
12 targets in 84s and fixed the bulk: RTX 5080 ₹5,080 → ₹1,54,499, RX 7600 XT ₹7,600
→ ₹34,999. That took the store-wide rate from 57% to 5%.

The remaining 5% were rows the listing pages no longer carry — out of stock on the
site, or past a target's `max_pages` — so a category scrape can never reach them, and
they kept their pre-fix prices. `scripts/repair_unseen_products.py` fetches those
products' own pages instead. It identifies them from **price_history, not
`products.updated_at`**: `save()` writes a history row on every scrape even when the
product row is unchanged, so "no history row since the run began" is the only precise
test for "never seen" — `updated_at` cannot separate *not seen* from *seen and
identical*. That distinction mattered: `updated_at` suggested 1,152 stale rows, while
the real figure was 123.

It corrected 89 of those 123, with no failures: PNY RTX 5000 Ada ₹5,000 → ₹4,59,999,
PNY RTX PRO 4000 Blackwell ₹4,000 → ₹2,14,999, ASUS ROG MAXIMUS Z890 HERO ₹1,851 →
₹58,999. Not all corrections were upward — Coconut clip fans went ₹1,200 → ₹239,
since the title number had been overstating them.

**Verified: 0 of all 2,042 Computech products now carry a price matching a number in
their own title, down from 57%.**

**TLG Gaming (sid 11) has no usable prices at all.** All 163 of its products are
priced 0.00 while flagged in stock. A zero is not a cheap price, it is a failed
scrape, and it led every price-ascending sort while silently subtracting a whole
component from any build total that included one — a ₹0 part was reachable from the
builder's candidate list. `api/filters.has_usable_price()` now excludes unpriced
listings from both the catalog (overridable with `include_unpriced=true`) and the
builder (not overridable — an unpriced part cannot belong in a costed build). That is
a guard, not a fix; TLG's parser is still wrong.

**What shipped alongside**
- `sort=price_asc|price_desc|name_asc|recent` on `/products`, with `NULLS LAST` so
  unpriced rows never lead, and `id` appended as a tiebreaker — offset pagination over
  a non-unique key was unstable, since a whole scrape batch shares one `updated_at`.
- **No `discount` sort, deliberately.** Indian retailers inflate MRP to manufacture a
  headline discount, so ordering by `mrp - price` would rank the least honest listings
  first.
- Search now matches per token against both the title as written and the title with
  punctuation stripped, so "rtx4070", "rtx 4070" and "4070 gigabyte" all find the same
  card. Previously only the exact spelling the shopper typed would match.
- The Stores tab and the catalog's retailer count now come from `/api/v1/stores`. Both
  were hand-written, so the page claimed 10 retailers while listing 4.

### TLG Gaming had no prices at all (2026-08-17)

All 163 of TLG Gaming's (sid 11) products were priced 0.00 while flagged in stock, so
the whole store contributed nothing and `has_usable_price()` was hiding it entirely.
Two causes, both in the price path:

- The store writes `Rs.31,999.00`, not `₹31,999`. `_clean_price` only stripped `₹` and
  commas, then handed the rest to `Decimal()`, which raised — and the fallback answered
  `0`. It now takes the **first** money-looking amount out of the string regardless of
  currency prefix, so `Rs.`, `INR` and bare digits all parse.
- The configured `price` selector was `.price-new, .price`, but `.price` is a
  *container* holding both the selling price and the tax line, giving
  `"Rs.31,999.00Ex Tax:Rs.27,117.80"`. Narrowed to `.price-new, .price-normal`, which
  hold the selling price alone (Journal 3 uses `-new` only when discounted).

Re-scraped in 4.2s, then `repair_unseen_products.py` fixed the 10 the listing pages
don't carry. **Catalog-wide unpriced products: 0 of 11,822.**

### Category leaks and the dead title fallback (2026-08-17)

`get_p_category()` returned `"Accessories"` immediately whenever the store supplied no
category, ignoring the `title` argument entirely — the long-standing open item. That
buried real parts: an AMD Radeon Pro W7700, a Sapphire RX 9070 XT, a Gigabyte Z890
board, 4 DDR5 kits and 10 internal surveillance drives were all sitting in Accessories,
invisible to both the catalog and the builder. `_classify_from_title()` now runs
whenever the raw category is missing or unmapped, using high-confidence markers only
and still falling back to Accessories when nothing is certain. 17 products recovered.

Also added a removable-media guard: a SanDisk 128GB memory card was filed by the store
under "Graphics Card" and was the cheapest GPU in the catalog.

A first attempt reclassified in bulk and moved a genuine W7700 *into* Accessories
before being caught — worth noting that a blanket re-run of the classifier is not safe
on rows whose `p_category` was corrected by hand earlier.

### Spec filters (2026-08-17)

The nine `*_specs` tables held 6,951 extracted model rows that nothing ever exposed, so
the catalog could be searched by title and nothing else. `api/spec_filters.py` maps each
category to its spec table and the fields worth narrowing by; `/products` accepts
`spec_<field>=`, `spec_<field>_min=` and `spec_<field>_max=`, joining on `canonical_id`.

`/products/facets?p_category=…` drives the UI from the catalog itself — enum options
carry counts, range fields carry observed bounds — so a filter can never offer a value
that returns nothing, and newly extracted specs appear without a code change. Unknown
`spec_*` names are ignored rather than rejected, so a stale bookmark degrades to a
broader search instead of a 422.

Building the facets surfaced three data defects that had no visible symptom before:
- **`psu_specs.wattage` was 100% NULL** (446/446), so the most useful PSU filter simply
  didn't appear. `psu_title_extractions.wattage` had held it all along (980 of 1,016
  rows); `populate_psu_wattage_from_extractions.py` backfilled 411 at zero API cost.
- A GPU claiming **12,000 GB of VRAM** (MB read as GB), another at 128, and 4 at zero.
- A RAM kit at **32 MHz** — a model-number digit read as the speed.

  All nulled rather than guessed, consistent with how the PSU efficiency gaps were left.

### Stage-1 data never reached the spec tables (2026-08-17)

Auditing every `*_specs` column for NULL density found key fields at **0%**:
`motherboard_specs.socket` (0 of 1,213), `cabinet_specs.form_factor`,
`cooler_specs.cooler_type`, and PSU wattage. The values had been extracted all along -
`motherboard_title_extractions.socket` was populated - but nothing ever copied stage 1
into stage 2. It stayed invisible because `CompatibilityEngine` reads the extraction
tables directly, so the builder worked correctly while the catalog offered **no
motherboard filters at all**.

`scripts/populate_specs_from_extractions.py` backfills all nine categories at zero API
cost: socket 917, memory_type 913, motherboard form_factor 857, cabinet form_factor
1,296, cooler_type 585, fan_size 377.

It validates before writing. A first run would have re-introduced a "32 MHz" RAM kit
that had just been cleared, because the bad value originates in the extraction table -
so `BOUNDS` rejects physically impossible readings and leaves the column NULL instead.
That also caught 11 bad fan sizes.

A sweep of every numeric spec column against physical bounds found only 7 outliers in
the whole catalog, and two of the three classes were **not** defects: an ASUS SP6
server board really does have 12 DIMM slots, and the "610 Hz" monitor is real - the
title reads "Asus XG248QSG ACE 24.1 Inch 610Hz". Worth recording that the bounds were
wrong, not the data.

### PCStudio was storing truncated product names (2026-08-17)

The remaining outlier class did turn out to be real, and it was the largest data defect
found so far. Five RAM kits carried `latency_cl = 3`; the source titles read
`"Kingston Fury Beast RGB 16GB 6000MHz CL3..."`. The name itself was cut off.

**1,793 products - 15% of the catalog, all PCStudio - had truncated names.** The theme
clamps long titles, so the visible text ends in an ellipsis while the complete name
sits in a nested `<span title="...">`. The parser read the visible text. This corrupted
far more than display: search couldn't match past the cut, canonical keys are built
from the name, and spec extraction was reading incomplete text - "CL3" is where the
title stopped, not what the kit is.

`_full_title()` now prefers a `title`/`aria-label`/`alt` attribute, but **only** when
the visible text is actually elided and the attribute agrees with the visible prefix,
so a theme using `title` for a tooltip cannot overwrite a good name. Re-scraped
PCStudio, then repaired the stragglers from their product pages: **1,793 → 59, and 0 of
those are in stock.** 1,730 products were correctly re-queued for extraction, since
their names changed and their old specs came from the truncated text.

Fixed a second bug found while repairing: `parse_product` unwrapped a JSON-LD `image`
list but not an `ImageObject` dict, so `urljoin` raised `TypeError` on every PCStudio
product page.

**A mistake worth recording:** `repair_unseen_products.py` treated *any* exception as
"the listing is gone" and marked 61 in-stock products unavailable when that TypeError
fired. Marking a product unavailable is a claim about the store's inventory, so it must
come from the store - it now only acts on a 404/410 and reports anything else as a
failure, leaving the row untouched. Re-checked all 61 against the store afterwards:
they were genuinely out of stock, so the data was accidentally right and the reasoning
was wrong.

### Price history charts (2026-08-17)

`price_history` had been accumulating since 2026-07-27 — 322,484 rows, 10,359 products
with five or more snapshots — and the UI showed it as a raw table of every 15-minute
scrape, which is thousands of rows describing a line that mostly doesn't move.

`GET /products/{id}/price-series?days=` aggregates per day, carrying each day's low and
high so real intra-day movement still shows. Stats report what the listing has actually
sold for: `lowest`, `highest`, `at_lowest`, `pct_above_lowest`.

**The comparison is deliberately against the observed floor, never MRP.** Inflated MRP
is precisely the trick this is meant to see through, so "3.8% above its 90-day low of
₹22,399" is a claim we can stand behind, while "40% off MRP" would not be.

Chart is hand-built SVG (a line for the daily low, a shaded band for the day's range) —
the page has no build step, and one `<path>` is less code than adding a dependency.
Edge cases verified in the browser: a flat price would divide by zero and emit `NaN`
into the path, so `min == max` is widened; a single day shows stats without a chart;
a listing with no history says so.

### Data flow documentation (2026-08-17)

`docs/DATAFLOW.md` — the pipeline end to end (config → scrape → persist → classify →
identity extraction → specs → read paths → DAG), what every table holds and how it is
keyed, and the invariants the pipeline depends on. Written because the two-identity
model (`(sid, pid)` per listing vs `canonical_id` per model) is the thing that has to
be understood before any query here makes sense, and it wasn't written down anywhere.
Linked from `README.md` and `PROJECT_MAP.md`, and it lists the backup/experiment tables
that should be ignored.

### Frontend review round (2026-08-17)

Six issues reported after testing; findings below, several of which were not what they
first looked like.

**1. Product grid collapsed to one card per row.** Mine, from the filter sidebar. The
sidebar and grid share one CSS grid, and a hidden panel is `display:none` - so it
leaves the grid entirely and the product grid becomes the *first* item, landing in the
230px sidebar column. Fixed with a `no-filters` class that collapses the layout to one
column, applied on first paint as well as on category change (`loadFacets()` wasn't
called at init, so the first render was always wrong). Also cache-busted `style.css`,
which had no version parameter while `app.js` did - CSS changes were not reaching
browsers at all.

**2. A 7th-gen Core i5 led the CPU list.** Identity extraction had failed completely
(`series=''`, `canonical_id='cpu:unknown'`), and `is_cpu_legacy` only ever reads
extraction fields, so no rule fired. It now falls back to the title when the series is
blank - **per brand**, which is the important part: vendors write "3rd Gen"/"5th Gen"
in AMD titles too, so running the Intel parser over "AMD Ryzen 5 5600X 5th Gen" returns
5 and would have hidden a current Ryzen 5000 part. Four of the five apparent hits were
false positives of exactly that kind; only the Intel one was real.

**3. Missing images: an entire store.** Computech had no image for 2,041 of 2,042
products - the thumbnail sits one level above the element the parser treats as the
card, so `card.find("img")` found nothing. `_image_near()` now searches outward from
the product link and **stops as soon as an ancestor holds a second product link**,
because past that point the nearest image belongs to a neighbouring product. The bound
is the point of the method: an unbounded search is what once read an 80+ Gold rating
off an adjacent listing's carousel. Catalog-wide missing images: 124 of 11,822.

**4. "RePacked" (TPS Tech) and "Open Box" (Computech, EliteHubs, PrimeABGB).** TPS
Tech's pages don't define the term; the listings carry original brand warranty and a
7-day return window, which places it with open-box rather than used goods. These are
systematically cheaper, so with no way to tell them apart they win price comparisons
against sealed stock - an "AMD Ryzen 3 4100 Open Box OEM" was the cheapest CPU in the
catalog. Added `products.condition` (migration `c4a1f7e2d910`, NULL = sealed) with
`matching/condition_policy.py`, wired into the save path, backfilled 24 listings, shown
as a badge, and ranked below sealed stock in the builder. Flagged, not hidden - an
open-box Threadripper at a real discount is a legitimate buy.

**5. Storage interface filter offered 13 options for 7 real things** - "SATA" and
"SATA III", "NVMe Gen4"/"NVMe Gen 4.0"/"NVMe PCIe 4.0", plus "SSD" and "Unknown", which
aren't interfaces. `VALUE_ALIASES` and `NON_VALUES` in the backfill script normalize on
write and re-tidy existing rows on every run. Now 7 options; "Unknown" is gone from
every category's filters.

**6. The two cooler URLs — two separate problems, one of which is not ours.**
- Computech genuinely publishes **₹99,999** for that cooler; the live page says so. Our
  scrape is accurate and the price is the retailer's placeholder. 18 listings sit at
  exactly 99,999 and 4 at 999,999. Left as-is: it is what the shop says. (₹9,999 is a
  normal price and was correctly left alone.)
- The real bug is a **canonical split**: PCStudio's listing keys as
  `cooler:cooler_master:masterliquid_core_lcd` while the other three key as
  `..._lcd_360`, so Compare cannot group them. 62 such prefix pairs exist catalog-wide.
  **Not merged**, because the short key is genuinely ambiguous: `adata:levante_ii` has
  both `_240` and `_360` candidates, and `kingston:nv3` vs `nv3_2230` are different form
  factors. This needs re-extraction, not a mechanical merge - recorded as open work.

A cross-store outlier check (listing ≥4× the median of its own model, 3+ listings)
returned only 4 hits, and two of those - two independent stores agreeing on ~₹35,700
for a "Dawg Y 990" against a ₹5,674 median - indicate the *median* is wrong, i.e. more
canonical merging of different products. Useful signal, same root cause as above.

### UI credibility pass (2026-08-17)

The brief was that it shouldn't look fake. The substantive problem was not styling: a
product card never said **which retailer the price came from**, which on a price
comparison site is both the missing trust signal and unusable information - you cannot
buy from "somewhere". Cards now carry the retailer, stock state, a saving badge, and a
proper "No image" placeholder rather than a broken-image glyph.

Added `/products/stats` and a stat bar (components tracked, retailers, price snapshots,
last updated). Every figure is fetched; the bar hides itself if the call fails rather
than showing placeholder dashes. Hardcoded numbers are the fastest way to look
fabricated and go stale the moment a retailer is added.

Toned down the template tells: gradient-text wordmark, 2.75rem hero, neon-cyan prices,
and cards that lift-and-glow on hover. Density raised instead (232px columns, 140px
images, tighter cards) - a catalog should read like something you scan, not a landing
page.

### Picker reworked: model first, then store (2026-08-17)

The builder's picker listed every *listing*, so "Asus Dual RX 9060 XT 16GB" appeared
four times at ₹53,990 / ₹54,662 / ₹56,000 / ₹69,999 — the same card at four shops
presented as four unrelated choices. Searching "9060 XT 16GB" returned 15 rows for 7
cards; the category as a whole holds 51 listings across 25 models.

That asks for two decisions at once — *which card* and *where to buy* — out of one
undifferentiated list, and whichever row gets clicked sets the retailer as a side
effect. `/builder/candidates` now returns one entry per `canonical_id` with its store
offers nested: models ordered by best price, offers within a model by price, the
cheapest tagged. `group_by_model: false` keeps the flat shape.

Listings with no `canonical_id` become their own group keyed by product id. Guessing
that two unidentified parts are the same model would merge genuinely different
products, which is a mistake this codebase has already paid for twice.

**Two assumptions corrected while doing this:**
- The builder was **not** auto-selecting the cheapest store. `_rank_candidates` sorted
  by condition then PSU tier and nothing else, so the leading row was effectively
  database order — arbitrary, not cheapest. Whatever the user clicked was always the
  exact listing used.
- The sidebar said **"Total Lowest Build Cost"** while `validate_and_calculate_build`
  simply sums the chosen listings. Nothing searched for a cheaper store, so the label
  was a claim the code never made good on. Now "Total for selected offers".

Grouping supersedes the old flat sealed-above-opened rule: models are ordered by price,
so a cheaper repacked model can lead and the badge says so. The guarantee that still
holds is *within* a model — at equal price, sealed stock is offered first.

### Stores tab demoted to a footer (2026-08-17)

A static list of ten shop names with no interaction and no reason to return to it does
not earn a nav slot. The information is worth keeping — it answers "who do you cover?",
which is a trust question — so it moved to a site footer alongside a note that prices
are scraped and we are not affiliated with any retailer. Coverage is also in the stat
bar, and every product card now names its retailer.

It earns a tab back when it carries something worth visiting for: per-store reliability
(whose "in stock" actually holds), which is already on the roadmap.

### Catalog: models not listings, and it can be paged (2026-08-17)

Two gaps, both structural:

**No pagination existed at all.** `app.js` fetched a hardcoded `size=40` with no `page`
parameter, so 11,449 products were browsable forty at a time and everything past that
was unreachable unless you happened to guess a narrowing search term.

**The catalog listed every listing.** Searching "9060 XT 16GB" returned 56 near-identical
cards for ~25 actual cards, the same product repeated once per shop — precisely the
duplication a comparison site exists to collapse.

`GET /products/models` aggregates by `canonical_id` **in SQL**, so paging is over models
rather than listings: 11,449 listings → 6,148 models, 257 pages of 24. Grouping a page of
listings in Python instead would have produced pages of wildly differing size and missed
cheaper offers sitting past the page boundary. Each card reads "from ₹X · N stores ·
cheapest <shop>", with the spread shown when offers differ.

Also added: budget min/max and a retailer dropdown (the API had accepted both all along),
and **URL state** — `?q=…&category=…&spec_socket=AM5&page=2` — so a result set can be
shared, bookmarked and reached with the back button. Every filter change resets to page 1;
staying on page 7 of a shorter result set renders an empty grid and looks broken.

### Filters are now hierarchical (2026-08-17)

Filters were computed independently of each other, so Motherboard offered all 72 chipsets
regardless of socket and most of them returned nothing once a socket was chosen.

`SPEC_FILTERS` field order is now the *display* order, deliberately arranged so each
category leads with the decision that constrains the rest — socket before form factor
before chipset; wattage before efficiency; brand always last, since it narrows least and
is what shoppers are most flexible about. `/products/facets` accepts the current selection
and computes every facet against it:

| Selection | chipsets | memory_type | brands | models |
|---|---|---|---|---|
| none | 72 | 2 | 11 | 905 |
| socket=AM5 | 22 | **1** (DDR5 — correct for AM5) | 10 | 374 |
| + form_factor=ITX | 5 | 1 | 4 | 16 |

Each facet is computed with every other filter applied but **not its own**. That is what
lets someone switch AM5 → LGA1700 directly; a self-constraining facet would collapse to
the single value already chosen and force a clear first. Skipping a filter leaves
everything below it wide, so a shopper with no socket preference can go straight to form
factor — verified: ITX alone gives 31 models, ITX on AM5 gives 16.

Supporting UI: active selections render as individually removable chips (with chained
filters, the panel alone doesn't convey how narrow a search has become once a lower
filter has collapsed to one option), and any list over 8 options is capped with a "Show
all N" toggle — a 72-entry dropdown is a wall regardless of how well it is ordered.

**Accessories** added as a category chip: 53 models. It has no spec table, so the facet
endpoint returns nothing, the panel hides, and the grid takes the full width — which the
`no-filters` layout fix from earlier already handled correctly.

### Spec value normalization (2026-08-17)

Values reach the filters from free-text retailer titles via an LLM, so the same fact
arrived spelled many ways. `src/matching/spec_value_normalizer.py` now owns the canonical
forms, replacing alias tables that had been accreting inside the backfill script.

| Filter | Before | After | What was wrong |
|---|---|---|---|
| Monitor resolution | 42 | 18 | Four naming systems at once — labels, pixel pairs, marketing names, and one mojibake entry where the separator had been corrupted upstream |
| Motherboard chipset | 72 | 45 | Form factor baked into the chipset name: `B850`/`B850M`/`B850I` were three options for one chipset |
| GPU chipset | 53 | 45 | `RX 9060 XT` vs `RX 9060XT` split one card's offers in two; `GTX 710` was never a product |
| Cabinet brand | 48 | 36 | Case variants, plus `Thermaltek` — a genuine typo, not a manufacturer |
| Storage brand | 39 | 33 | `WD` vs `Western Digital`, `Patriot` vs `Patriot Memory` |
| RAM brand | 36 | 23 | `TeamGroup` four ways, `G.Skill` four ways |
| PSU brand | 36 | 24 | `ProLab Design` four ways |
| Storage interface | 13 | 7 | `SATA`/`SATA III`, three spellings of NVMe Gen4 |
| PSU modularity | 5 | 3 | `Modular`/`Fully Modular`/`Full` |

Two rules throughout, and they are the whole design:

- **Only collapse what is genuinely the same.** `B650E` survives because it is a
  different chipset from `B650`, while a trailing `M`/`I` is stripped because those are
  form factors and `form_factor` is already its own filter. Sub-brands stay separate:
  XPG is ADATA's memory line, but people search "XPG", so folding it in would lose a
  search term without shortening any filter meaningfully.
- **A value that says nothing becomes NULL.** Applied to every column rather than per
  field, which is how "Unknown" stayed out of all nine categories instead of being
  handled eight times and forgotten in the ninth.

Values removed for being in the wrong filter entirely: `SP5`/`SP6` (sockets, sitting in
chipset), `DDR6`/`DDR7`/`SDR` (no GPU ships these), `Curved`/`Ultrawide Curved`/`LED`
(shape and backlight, not panel technology), `SSD` (says what a drive is, not how it
connects), and `Cybenetics Bronze`/bare `80+` (a different certification scheme, and a
tier claim that names no tier).

**Monitor was missing from `MAPPINGS` entirely** — the root cause of it being the one
category still offering "Unknown" brands and 42 resolutions. Nothing had ever normalized
it. 100 tests in `tests/test_spec_value_normalizer.py`, every case a real catalog value.

Also fixed: `repair_unseen_products.py` never wrote `image_url`, so anything repaired via
its product page kept no picture — which is why Computech still had imageless cards after
a full re-scrape. The 8 in-stock cases are filled; missing images across the catalog are
now 116 of 11,824, all out of stock.

### Mobile filter drawer (2026-08-17)

Below 860px the sidebar had been stacking above the grid, pushing every result below the
fold. It is now a drawer — the pattern faceted-search guidance recommends for narrow
screens — with the page behind it locked from scrolling. Verified at 375px: results stay
visible, all six motherboard filters reachable, body unlocks on close.

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
10. **PSU efficiency — 77 → 48 missing (2026-08-16).** Three sources used in order:
    - **Official 80 PLUS registry** (CLEAResult export, 14,371 units, `data/raw/All_certified_psus.xlsx`, imported by `scripts/import_80plus_efficiency.py`): closed 5. Validated by running the matcher against PSUs that already had Cybenetics ratings — matched 129/446 and **agreed with Cybenetics on 99 of 124**.
    - **Retailer product pages** (`scripts/scrape_psu_efficiency.py`): closed 24 more. Titles omit the rating that the page body states plainly.
    - The remaining 48 pages state no rating at all; those units may genuinely be uncertified, so they stay null.

    Two extraction traps caught while building the scraper, both of which produced confident wrong answers before being fixed:
    - A whole-page regex read ratings off **related-product carousels**. An Ant Esports "Value Series" unit came back 80+ Gold from a neighbouring Corsair listing. Extraction is now anchored to the product's own model number and there is **no unanchored fallback** — 18 already-written rows were reverted when this was found.
    - Anchoring alone wasn't enough: taking the *first* tier inside the window still read a preceding cross-sell line. It now takes the tier **physically closest** to the model mention.
    - The unanchored rows exposed something worse: two of them (`psu:16700`, `psu:16742`) were a **Sennheiser soundbar and a Marshall speaker** mis-filed into Power Supply, each landing a rating from a page carrying three different tiers. The classifier now routes audio gear to Accessories, and the 3 affected products were recategorised.

    Researched the remaining 46 against the official registry and the web: only **one** was findable (MSI MEG Ai1600T, Titanium - the catalog title mangles "Ai1600T" to "A1600T"). The rest are genuinely absent from the 80 PLUS registry, which matches what they are: budget value-line units. Thermaltake's Litepower Gen3 siblings certify only as Standard, Zebronics certifies its PGP line but not VS/ZS, and Gamdias certifies KRATOS M1/P1 but not the E1. So "no rating" is the correct answer for most, not missing data.

    Two consequences, both applied:
    - **Uncertified PSUs now rank last** in the builder's picker (`_rank_candidates`). Ranking by certification rather than by a brand blocklist keeps the judgement on the product, and any unit that later gains a verified rating rises automatically. A PSU is the part whose failure can damage everything attached to it, so this is the one slot where an unknown-quality option shouldn't lead.
    - **PSUs with no resolved brand are hidden entirely** (43 listings across 29 models). Identity extraction couldn't name them, and two turned out not to be power supplies at all. Several are real regional makes (Dawg, Coconut) the model doesn't recognise yet, so this is a recognition gap rather than a verdict on the brands - they return as soon as extraction can name them.

    Still open: the **PSU canonical key is too coarse**. ASUS sells "TUF Gaming 750W" in both Bronze and Gold trims, Antec's HCG750 likewise, but the key is only brand+model+wattage so the variants collapse into one model and inherit whichever rating was written last — the same defect as the B850/B850I motherboard merge. Both importers therefore only fill gaps and never overwrite. Fixing it means adding the efficiency trim to the PSU canonical key and re-running identity extraction.
