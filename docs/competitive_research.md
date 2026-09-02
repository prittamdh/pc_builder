# Competitive & Product Research

Started 2026-08-17. Living document.

Status legend: **[verified]** = read directly from source or codebase.
**[search]** = from search-result summaries, not read first-hand. **[knowledge]** = model
knowledge, not verified this session. **[pending]** = awaiting capture.

---

## 1. The ratings / rating-count decision

**Recommendation: do not build per-product star ratings.**

Evidence:

- **[verified]** No `rating` or `rating_count` column exists. `src/db/models/product.py`
  has no such field. Every "rating" match in the repo is *80 PLUS efficiency rating*.
- **[verified]** The source data is absent. `generic_parser.py:349` already parses Product
  JSON-LD — the standard home of `aggregateRating`/`reviewCount`. Grepping the three saved
  retailer pages in the repo root (`mdcomputers.html`, `product.html`, `pcstudio_search.html`)
  returns **zero** occurrences of `aggregateRating`, `ratingValue`, or `reviewCount`.
- **[verified]** It conflicts with the canonical layer. The system's value is collapsing one
  GPU across ten stores into a single `canonical_id`. A star rating is a property of a
  *listing*, not a *model*. Averaging 4.2 (n=11) and 3.8 (n=4) from two unverifiable
  populations yields a number that looks authoritative and is not.
- **[verified]** PcPaisa, the closest Indian competitor, does not show ratings either.

This is the same failure mode already documented in `PROGRESS.md`: the PSU carousel
contamination, where a confident wrong value was worse than a null.

### Build these instead

1. **Objective quality tiers.** The 80 PLUS work is the proven pattern — external registry,
   validated (99/124 agreement with Cybenetics), feeding `_rank_candidates`. Extend per
   category rather than importing crowd noise.
2. **Price-history trust signals.** `price_history` across 10 stores is an asset no Indian
   competitor has surfaced. "Lowest in 90 days", "up 8% this week", and — the India-specific
   one — detecting the fake-MRP game by testing `mrp` against the real 90-day floor.
3. **Per-store reliability.** Repeated scrapes let you measure whose "in stock" holds and
   whose listed price matches at checkout. Store-level sample sizes are large enough to be
   honest, unlike per-product review counts.

### If ratings are built anyway

Nullable per-listing fields on `products`; never promoted to the canonical or
`*_title_extractions` layer; displayed only with `n` visible and above a threshold; excluded
from `_rank_candidates`.

---

## 2. Current state of our app — audit

**[verified]** All from reading the source this session.

### Frontend (`src/static/`, 189 HTML + 511 JS + 469 CSS lines)

Three tabs: Catalog & Search, PC Builder, Stores. Three modals: component select,
multi-store compare, price history.

| Gap | Detail |
|---|---|
| **No sorting, anywhere** | `products.py:68` hardcodes `order_by(Product.updated_at.desc())`. There is no sort parameter. A price-comparison tool where you cannot sort by price is the single largest functional gap. |
| **No filters exposed** | The API supports `min_price`, `max_price`, `sid`, `in_stock`; the UI exposes none. Only free-text search + 10 category chips. |
| **No spec filters at all** | 9 spec tables + `*_title_extractions` hold 6,951 model rows (socket, TDP, VRAM, form factor, wattage, efficiency). None are queryable. This is PCPartPicker's core UX and our data is already there. |
| **Stores tab hardcoded to 4** | `index.html:116-137` lists MDComputers, PCStudio, Vedant, PrimeABGB as static HTML — while the hero on line 30 says "10 Indian retailers" and `GET /api/v1/stores` exists and returns all of them. |
| **Weak search** | `Product.name.ilike('%q%')` only. No relevance ranking, no fuzzy/trigram. "4070" matches; "rtx4070" does not. |
| **No product detail page** | Compare and history are modals only; nothing is linkable or shareable per product. |
| **Possible dead CSS** | `index.html:7` loads `/static/style.css`; `index.css` also exists. |
| **Untested on narrow viewports** | Already flagged as open item 9 in `PROGRESS.md`. |

### What is genuinely strong

- 10 retailers live, ~11,000 in-stock products, composite `(sid, pid)` identity.
- Real compatibility engine (socket, RAM generation, case fit, TDP/wattage).
- Canonical identity layer merging duplicate listings across stores.
- `price_history` accumulating across all stores.
- Saved/shareable builds re-priced and re-validated on every load, reporting drift.
- Legacy-platform policy hiding unbuildable parts without destroying price history.

---

## 3. Competitive landscape — the important finding

### PCPartPicker withdrew from India

**[search]** Forum thread *"Removing India support"*
(`pcpartpicker.com/forums/topic/397308`). Retailers were delisted for "persistently bad
price data" and international-support complexity; the last remaining retailer referred
almost no sales. Listing prices requires a negotiated retailer agreement.

Reading: the incumbent did not fail to fit India — it *exited*. Its model depends on
retailer relationships. Ours depends on scraping, which is exactly why we can cover a market
it could not.

### The market is more crowded than assumed

| Site | Coverage | Notes |
|---|---|---|
| **PcPaisa** (`pcpaisa.in`) **[verified]** | **18 retailers** | The closest competitor. 5 overlap with ours: Vedant, Computech, PrimeABGB, MDComputers, TPSTech. Also TheITDepot. ~1,912 deal candidates, 16 categories. Build planner with live total + compatibility warnings. **"Safe deal filter" rejecting suspicious fake-MRP drops.** Telegram price alerts, Discord, WhatsApp channel, budget build guides. **Does not have: ratings/reviews, detailed price-history charts, stock-reliability indicators.** |
| **PickPCParts** (`pickpcparts.in`) **[search]** | Indian retailers | Claims retailer partnerships for pricing/availability, compatibility checking, price history, build guides. Cloudflare-protected; not yet read directly. |
| **PartsRadar** **[search]** | India | AI-powered tracker. Founded explicitly because "prices weren't consistent, stock info was unreliable, and comparing everything took forever." |
| **BuildCores** **[search]** | International | PC price comparison feature. |

**Implications.**

- We are not first. Differentiation has to be earned, not assumed.
- PcPaisa already ships the fake-MRP filter — independent confirmation that it is the right
  India-specific feature, and that it is table stakes rather than a moat.
- **The three things PcPaisa lacks are the three we are best positioned for:** real
  price-history charts (we have the table), stock reliability (we have repeated scrapes),
  and genuine spec-level compatibility depth (we have 6,951 extracted model spec rows and a
  real compatibility engine, not just warnings).
- Retailer count is a visible scoreboard: 18 vs our 10. TheITDepot is an obvious addition.
- Distribution matters as much as product: they run Telegram/Discord/WhatsApp. We are not
  competing on that axis — alerts and notification channels are explicitly out of scope
  (see section 4). The bet is on depth of data instead: price history, stock reliability,
  and real compatibility.

---

## 4. What users actually ask for

### On PCPartPicker's own forums **[search]**

Price alerts dominate — many separate threads:

- Alerts on saved part *lists*, not just single parts.
- A threshold filter: only alert on drops greater than N%.
- Alerts when a build's **total** falls within budget.
- Parametric alerts driven by the filter sidebar.
- Staff note the hard part: a part losing price data registers as ₹0 and fires false alerts.

> **Not building this.** Decided by the project owner on 2026-08-17. Recorded here
> because the demand signal is real and unambiguous, so the decision should be a
> deliberate one to revisit rather than an oversight to rediscover. Alerts also carry
> ongoing delivery cost (email/Telegram, scheduling, unsubscribe handling) and a
> correctness trap PCPartPicker's own staff flagged — an unpriced part reads as ₹0 and
> fires a false "price drop". The ₹0 guard (`has_usable_price()`) exists regardless,
> since sorting and build totals need it either way.

### Complaints about PCPartPicker **[search]**

- Missing parts; catalog gaps.
- No physical-space calculation ("will this fit in this tower"). **We already do case fit,
  and GPU clearance is partially blocked on `max_gpu_length_mm` coverage — 5/1,405 models.**
- Save UX: only "save as", no update; users lost lists.
- Blank prices, stale stock, "no longer available".
- Dislike of a recent redesign — compressed, over-outlined, zoomed-in.

### India-specific **[search]**

- The MRP system is widely described as broken: inflated MRPs manufacture fake discounts.
- Inconsistent pricing and unreliable stock information across retailers are the stated
  founding motivations of at least two competitors.

---

## 5. PCPartPicker teardown

**[pending]** — pcpartpicker.com returns 403 to server-side fetching (Cloudflare), as do
its forums and pickpcparts.in. Reddit blocks it too, and no Chrome extension is connected.
Awaiting user-supplied captures of: `/list/`, `/products/cpu/`, a product page, `/trends/`,
and a completed-build permalink.

---

## 6. Note on tooling

The in-app Browser pane crashed the desktop app twice on `pcpartpicker.com/list/`
(2026-08-16, sessions `a4fd3014` → `dc88c0a3`). No Crashpad minidump and no Windows
Application Error event were produced, which points to an OOM termination rather than a
native fault. Contributing: a 14.3 MB / 6,371-entry session transcript rendered in the same
Electron process, plus WSL/Docker memory pressure. Avoid pointing the built-in browser at
heavily script-protected sites.
