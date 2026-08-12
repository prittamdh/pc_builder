# Task: Canonical Part Resolution & Cross-Retailer Matching for PartsRadar

## Context

PartsRadar scrapes PC component listings from multiple Indian retailers. The same
physical product (e.g. "Intel Core i7-14700 Processor") appears under many raw
titles across stores — different casing, spacing, word order, and added marketing
text. Currently spec extraction runs per-listing, which means the same product gets
re-extracted (and re-hallucination-checked) once per store.

Goal: build a **canonical parts layer** that sits between raw scraped listings and
spec extraction, so each real-world product is identified, keyed, and spec-extracted
exactly once — regardless of how many stores list it. Listings then attach to a
canonical part as (store, price, url, stock, scraped_at) records.

Existing pipeline to build on (do not discard, extend):
- `normalize.py` — title normalization / cleanup
- `schemas.py` — category-specific attribute schemas
- `match.py` — current matching logic

## Core Architecture

```
raw_listing_title
      │
      ▼
normalize_title(title, category)         # existing normalize.py, extend as needed
      │
      ▼
build_canonical_key(normalized, category) # NEW — category-specific key rules below
      │
      ▼
resolve_canonical(key, category)          # NEW — exact match → fuzzy match → create new
      │
      ├─ existing canonical_id found ──► attach listing, done (no LLM call)
      │
      └─ no match ──► spec extraction (LLM/regex) ──► create canonical part ──► attach listing
```

**Key principle: spec extraction only ever runs on CREATE, never on re-match.**
Every subsequent listing for the same product is a cheap key lookup, not an LLM call.

## Canonical Key Rules Per Category

Implement `build_canonical_key(normalized_title, category) -> dict` returning the
minimal field set that defines uniqueness for that category. Two listings with the
same key are the same product; do not add extra fields into the key beyond what's
listed (extra fields cause false negatives / duplicate canonical parts).

| Category | Canonical Key Fields | Notes |
|---|---|---|
| CPU | `brand + model_number` | Only Intel/AMD. Simplest category — no variant tier. |
| PSU | `brand + model_number + wattage` | Deterministic, no AIB-style variance. |
| Cooler | `brand + model_number` | Type (air/AIO/size) is spec, not key — don't extract, it's implied by category + model. |
| Case | `brand + model_number` | Same pattern as cooler. |
| Storage (SSD/HDD) | `brand + series + capacity + interface` | Interface = NVMe Gen3/Gen4/SATA — must be in key, capacity variants are genuinely different SKUs. |
| RAM | `brand + series + capacity + speed_mhz + cl_timing` | Do NOT collapse different capacity/speed into one canonical part — these are different SKUs even if same series. |
| Motherboard | `brand + chipset + model_number` | Chipset (B650/Z790/etc.) is a **spec-donor** — see two-tier note below. |
| GPU | `aib_brand + variant_model + chipset` | Two-tier — see below. This is the one genuinely complex category. |

### GPU / Motherboard: Two-Tier Chipset Inheritance

GPU and motherboard both have a shared "chipset" layer whose specs apply to many
SKUs, plus per-variant deltas. Model this as two tables, not one flat schema:

**Tier 1 — `chipset_specs` table** (e.g. keyed by `RTX 4070`, `B650`)
- Extracted/looked-up ONCE per chipset, ever.
- GPU chipset specs: CUDA/stream cores, VRAM size + type, bus width, base architecture, TDP reference.
- Motherboard chipset specs: socket, RAM support (type/max speed/max capacity), PCIe gen, supported CPU generations.

**Tier 2 — `canonical_parts` table** (e.g. `ASUS TUF Gaming RTX 4070 OC`)
- Extracted per variant, but ONLY the fields that actually vary from chipset defaults:
  - GPU: aib_brand, factory clock speed (if OC), cooling (fan count/size), card length, slot width, power connector, price tier.
  - Motherboard: form factor, VRM quality tier, M.2 slot count, rear I/O specifics.
- At read time: `final_specs = {**chipset_specs[chipset_id], **variant_overrides}`

This means variant extraction prompts should be small (only ask for the delta fields),
and chipset extraction is rare (few hundred chipsets total vs. thousands of listings).

## Matching Pipeline Logic

Implement in `match.py`:

```python
def resolve_canonical(title: str, category: str) -> str:
    """Returns canonical_id, creating a new canonical part if none exists."""
    normalized = normalize_title(title, category)
    key = build_canonical_key(normalized, category)

    # 1. Exact match on normalized key
    exact = canonical_db.exact_lookup(key, category)
    if exact:
        return exact.canonical_id

    # 2. Fuzzy match — catches cross-store spelling/spacing variance
    #    e.g. "Ryzen 9 9900X" vs "RYZEN9-9900X" vs "AMD 9900X Ryzen 9 CPU"
    candidates = canonical_db.fuzzy_lookup(key, category, top_k=5)
    if candidates and candidates[0].score >= FUZZY_MATCH_THRESHOLD:
        return candidates[0].canonical_id

    # 3. No match — extract specs and create new canonical part
    if category in ("gpu", "motherboard"):
        chipset_id = resolve_or_create_chipset(key, category)
        variant_specs = extract_variant_deltas(normalized, category, chipset_id)
        return canonical_db.create(key, category, chipset_id=chipset_id, specs=variant_specs, status="NEEDS_REVIEW" if low_confidence else "OK")
    else:
        specs = extract_specs(normalized, category)  # existing extraction, only runs here
        return canonical_db.create(key, category, specs=specs, status="NEEDS_REVIEW" if low_confidence else "OK")
```

Tune `FUZZY_MATCH_THRESHOLD` empirically (start ~0.90 on token-sort ratio) — false
positives here silently merge two different SKUs, which is worse than a false
negative (which just creates a duplicate flagged for review).

## Database Schema Additions

```sql
CREATE TABLE chipset_specs (
    chipset_id TEXT PRIMARY KEY,      -- e.g. "rtx_4070", "b650"
    category TEXT NOT NULL,           -- "gpu" | "motherboard"
    specs JSONB NOT NULL,
    source TEXT NOT NULL,             -- "manufacturer_spec_page" | "llm_lookup" | "manual"
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE canonical_parts (
    canonical_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    brand TEXT NOT NULL,
    key_fields JSONB NOT NULL,        -- the exact fields used in build_canonical_key
    specs JSONB NOT NULL,             -- variant-level specs (or full specs for non-tiered categories)
    chipset_id TEXT REFERENCES chipset_specs(chipset_id),  -- NULL for non-GPU/mobo
    from_title TEXT[] NOT NULL,       -- which fields came from the title vs. inferred
    status TEXT NOT NULL DEFAULT 'OK', -- "OK" | "NEEDS_REVIEW"
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE listings (
    listing_id TEXT PRIMARY KEY,
    canonical_id TEXT REFERENCES canonical_parts(canonical_id) NOT NULL,
    store TEXT NOT NULL,
    raw_title TEXT NOT NULL,
    price NUMERIC,
    url TEXT,
    in_stock BOOLEAN,
    scraped_at TIMESTAMP NOT NULL,
    UNIQUE(store, url)
);
```

Idempotent upserts on `listings` keyed by `(store, url)` — matches your existing
Postgres upsert pattern, just attaching a `canonical_id` foreign key now instead of
storing specs redundantly per listing.

## Spec Extraction Rules (Reduce Hallucination + Tokens)

1. **Regex/deterministic extraction first**, always. Only call the LLM for fields
   regex genuinely can't get. Brand/model are almost always regex-extractable —
   never spend an LLM call re-deriving those.
2. **Two output buckets per extraction**, not per-field source tags:
   - `from_title`: array of field names literally present in the title text.
   - everything else in `specs` is implied/inferred — no per-field tagging needed.
3. **Ground inferred specs with a lookup tool, not LLM memory.** Build/maintain a
   small cached spec table (scraped once from Intel ARK / AMD spec pages / GPU
   chipset spec sheets) keyed by exact model number. LLM only free-generates specs
   when the model number isn't in the cache, and that result gets cached going
   forward. This directly prevents cases like the CPU core-count hallucination
   found in initial testing.
4. **Batch extraction calls**: when creating multiple new canonical parts in one
   scrape run, batch 15–25 titles into a single LLM call (JSON array in/out) rather
   than one call per title — schema/instructions get paid for once per batch, not
   once per title.
5. Category-specific schema sent to the LLM should be a compact JSON skeleton, not
   prose — and only include the fields relevant to that category (route via
   `p_category` first, same as existing categorization logic).

## Migration Mapping: Existing `products` Table

The current `products` table is effectively the **listings table** described above,
just without the canonical layer yet. Do not redesign it — extend it.

Current schema:
```
created_at, updated_at, id, sid, pid, name, product_url, image_url, brand,
category, description, specifications, currency, current_price, current_mrp,
in_stock, p_category
```

Mapping:

| Current column | Role | Treatment |
|---|---|---|
| `id` | PK | Becomes `listings.listing_id` conceptually — no change needed. |
| `sid` | store id | This is `listings.store`. |
| `pid` | store's product slug/id | Keep as-is — `(sid, pid)` is the natural idempotent upsert key, unchanged. |
| `name` | raw scraped title | Input to `normalize_title()` / `build_canonical_key()`. |
| `product_url`, `image_url` | listing detail | Stay on `products`, no change. |
| `current_price`, `current_mrp`, `in_stock` | listing-level, changes per scrape | Stay on `products`, no change. |
| `brand`, `category`, `p_category` | already extracted | Used to build the canonical key; `p_category` remains the routing field for which schema/normalizer to apply. |
| `description`, `specifications` | currently mostly empty (`"null"`) | Superseded by `canonical_parts.specs`. Stop writing per-listing specs here going forward; leave columns in place for backward compatibility unless a full cutover is wanted. |

**Required schema addition:**
```sql
ALTER TABLE products ADD COLUMN canonical_id TEXT REFERENCES canonical_parts(canonical_id);
CREATE INDEX idx_products_canonical_id ON products(canonical_id);
```

**Backfill procedure** (run once after `canonical_parts` table exists and
`resolve_canonical()` is implemented):

```python
for row in products.where(canonical_id IS NULL):
    key = build_canonical_key(normalize_title(row.name, row.p_category), row.p_category)
    canonical_id = resolve_canonical(key, row.p_category)  # creates new canonical part if none exists, else reuses
    products.update(id=row.id, canonical_id=canonical_id)
```

Existing `(sid, pid)` uniqueness constraint and upsert logic on `products` is
unaffected — this only adds a join target above it. New scrape runs should call
`resolve_canonical()` at insert/upsert time and populate `canonical_id` directly,
so the backfill above is only needed once for historical rows.

## Phased Task List for Antigravity

1. Extend `normalize.py` with category-aware normalization if not already parametrized by category.
2. Implement `build_canonical_key(normalized, category)` in `match.py` per the table above — start with CPU and PSU (simplest, no tier, validates the pipeline end to end).
3. Add `canonical_parts`, `listings`, `chipset_specs` tables (migration script).
4. Implement `resolve_canonical()` exact-match path first; wire it into the existing scrape → Postgres upsert flow for CPU category only, verify no regressions.
5. Add fuzzy matching (token-sort ratio) with a manual review queue for low-confidence matches (`status = NEEDS_REVIEW`), reusing existing NEEDS_REVIEW convention from category cleanup work.
6. Extend to PSU, Cooler, Case, Storage, RAM (all single-tier, same pattern as CPU).
7. Build chipset-tier logic for GPU and Motherboard: `resolve_or_create_chipset()`, `extract_variant_deltas()`, spec merge at read time.
8. Build/seed the cached spec lookup table for grounding (start with top N models by listing frequency — cover 80% of volume first).
9. Add batch extraction path for new-canonical-part creation during scrape runs.
10. Backfill: run existing scraped listings through the new pipeline to populate `canonical_parts` and re-point `listings.canonical_id`.

## Success Criteria

- Each unique real-world product has exactly one row in `canonical_parts`, regardless of how many stores list it.
- Spec extraction LLM calls scale with unique products, not with listing count.
- GPU/motherboard variant extraction prompts are visibly smaller than chipset extraction prompts (delta-only).
- `NEEDS_REVIEW` queue captures ambiguous fuzzy matches and low-confidence extractions for manual resolution rather than silently merging or duplicating.
