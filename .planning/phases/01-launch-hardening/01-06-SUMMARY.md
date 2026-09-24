# 01-06 SUMMARY: PSU benchmark script (AI-01)

**Date:** 2026-09-25 (fix round 1 appended same day)
**Files:** `scripts/benchmark_provider.py` (new), `tests/test_benchmark_provider.py` (new)
**Commits:** the manager committed the work described in Tasks 1-3 below as `10b9076`.
Fix round 1 (see bottom section) is *not yet committed* - it sits uncommitted on top
of `10b9076`, per this agent's own no-commit rule.

## What was built

`scripts/benchmark_provider.py`:
- `CASES`: 8 PSU titles with independently-verified `expected` tiers, each with a
  `trap` (what it tests) and an `evidence` field naming the registry row or
  manufacturer URL + quote + check date.
- `normalize_rating(value)`: case/whitespace/spelling-insensitive tier comparison;
  `None`/`""`/`"null"` all mean no tier.
- `score_results(cases, results)`: matches on the parsed `"index"` field (1-based),
  not array position; a missing/unparseable entry is wrong + one JSON failure.
- `run_benchmark(service, cases)`: one `extract_batch` call, timed with
  `time.monotonic`, returns score/n/json_failures/titles_per_min.
- `main(argv=None)`: `--provider NAME` (looked up in `provider_chain()`) or
  `--url/--model/--key-env`/`--key-env-optional` for an arbitrary OpenAI-compatible
  endpoint (Phase 8's local trial). `--runs K`. No `--key` value argument anywhere;
  keys only come from environment variables or the provider chain's own settings
  read. `service._fallbacks` is emptied immediately after construction so a run can
  never silently switch providers. Never imports `db.session`, never calls the
  DB-hint prompt builder - only the bare `PSU_IDENTITY_BATCH_PROMPT`.

`tests/test_benchmark_provider.py`: 27 offline tests (fake service, no network, no
DB) covering normalization edge cases, scoring edge cases (all-correct / one-wrong /
one-missing-index), `run_benchmark`'s timing and throughput, `main`'s provider
lookup/error paths, the no-DB-import guarantee (subprocess check), source-level
guarantees (no `identity_prompt` reference, no bare `--key` flag, `_fallbacks`
present), and answer-key integrity (every case has evidence, `len(CASES) == 8`, no
case title duplicates a few-shot prompt title).

## TDD evidence

RED: before `scripts/benchmark_provider.py` existed,
`python -m pytest -q tests/test_benchmark_provider.py` failed at collection with
`ModuleNotFoundError: No module named 'benchmark_provider'`.

GREEN: after implementing the script, `python -m pytest -q tests/test_benchmark_provider.py`
-> `27 passed in 3.00s`.

## Candidate verification table (Task 2)

Every answer was checked against `data/raw/All_certified_psus.xlsx` (via
`scripts/import_80plus_efficiency.py`'s own loader/matcher) or, when the registry
uses only internal SKU codes with no marketing name to match against, the
manufacturer's own product page (fetched read-only this session, quote + URL
recorded in the case's `evidence` field). Never the project's own
`psu_title_extractions` table (Pitfall 9).

| Candidate id(s) | Title | Expected | Evidence source | Status |
|---|---|---|---|---|
| 16593 | Super Flower LEADEX III GOLD UP 750W (Cybenetics trap) | 80+ Gold | Manufacturer page (super-flower.com.tw/products-detail/LIII-G/, model no. SF-750F14GE, "80 PLUS Gold Certified") + registry row SF-750F14GE/750W/Gold, agree | **Locked** |
| 3960 | MSI MAG A750GL PCIE5 750W (GL suffix, no tier word in title) | 80+ Gold | Registry: exact model+wattage match, single row, Gold | **Locked** |
| 20457 | MSI MAG A850GL PCIE5 850W | 80+ Gold | Registry: exact model+wattage match, single row, Gold | **Locked** |
| 17180 | duplicate listing of the same A850GL model | 80+ Gold | same as 20457 | Dropped - redundant duplicate listing, not needed once 20457 locked |
| 16759 / 18924 / 14917 | MSI MAG A650BN 650W (BN suffix) | 80+ Bronze (title's own claim) | Registry contains **two conflicting rows** for the identical model number "MAG A650BN" at 650W - one rated Silver, one rated Bronze - and no manufacturer page was found that resolves the conflict | **Dropped - registry itself is ambiguous, cannot independently verify** |
| 6186 | Corsair RM750E 750W (Cybenetics Gold, control case) | 80+ Gold | Registry: exact model ("RM750e")+wattage match, single tier (Gold) across two SKU rows | **Locked** |
| 16673 | Cooler Master MWE Gold 850 V3 (tier in model name) | 80+ Gold | Manufacturer page (coolermaster.com/en-global/products/mwe-gold-850-v3-atx-3-1.html): "80 PLUS Rating: 80 PLUS Gold" | **Locked** |
| 19204 | Cooler Master MWE Gold 850 V2 | 80+ Gold | same class of evidence as 16673 | Dropped - redundant with 16673, not needed once locked |
| 15310 | Thermaltake Toughpower GF A3 750W 80+ Gold | 80+ Gold | would be registry-verifiable, but... | **Dropped** - near-identical to `PSU_IDENTITY_BATCH_PROMPT`'s own few-shot example ("Thermaltake Toughpower GF A3 1050 Watt 80 Plus Gold ATX 3.0 SMPS"); using it would test memorization of the prompt's own example, not extraction |
| (search across Ant Esports/Antec/MSI/Thermaltake budget SMPS titles) | untiered candidate | expected `null` | Registry showed **zero** rows for the relevant brands (e.g. Ant Esports has no certified units at all) - suggestive but not conclusive; a search of the manufacturer's own site (antesports.com) did not surface a matching product page to quote from, so absence could not be confirmed from *both* required sources | **Dropped** per the owner's rule: "if absence can't be confirmed from both sources, don't include an untiered case" |
| 6248 / 20992 | Gigabyte P550SS 550W (added during verification, not in the original candidate list) | 80+ Silver | Registry: exact model ("GP-P550SS")+wattage match, single row, Silver | **Locked** - added for tier diversity, distinct wattage/SKU from the prompt's own Silver few-shot example (P650SS) |
| 17141 | SilverStone Strider Platinum ST1200-PTS 1200W (added) | 80+ Platinum | Registry: exact model+wattage match, single row, Platinum | **Locked** - added because no Platinum case existed after dropping the ambiguous Bronze candidates |
| 13046 | Corsair AX1600i 1600W (added) | 80+ Titanium | Registry: exact model+wattage match, single row, Titanium | **Locked** - added for the highest-tier diversity case |

**Final locked count: 8** (all independently verified; `CASE_COUNT == len(CASES) == 8`).

## Live runs (Task 3)

Both run via `PYTHONIOENCODING=utf-8 python scripts/benchmark_provider.py --provider <name> --runs 2`,
keys read from the local environment through `provider_chain()`/settings, never printed.

### mistral

```
Provider: mistral (ministral-14b-latest)
Score: 7/8
Titles/min: 80.6
JSON failures: 0
Score: 7/8
Titles/min: 78.8
JSON failures: 0
```

Miss (both runs, same case): case #3, "Corsair RM750E 750 Watt Cybenetics Gold Fully
Modular ATX 3.1 Power Supply (CP-9020295-IN)", expected `80+ Gold`. Mistral's raw
answer:
```
{'index': 3, 'brand': 'Corsair', 'model_number': 'RM750E', 'wattage': 750,
 'efficiency_rating': None, 'confidence': 'medium',
 'notes': 'Cybenetics rating ignored; no 80 PLUS tier specified'}
```
This is a real finding about `ministral-14b-latest`, not a bad case: the title states
only a Cybenetics tier (no "80 PLUS" wording anywhere), and the model correctly
followed the prompt's instruction to ignore Cybenetics - but then returned `null`
instead of recognizing that this specific SKU's real 80 PLUS certification (Gold,
independently confirmed in the registry) happens to match its stated Cybenetics
tier. Per the owner's rule, the case was **not** edited or dropped to make this pass
- it is flagged here for the owner as a genuine model-behavior gap, not a benchmark
defect. (`provider_chain()`'s docstring claims `ministral-14b-latest 8/8` on the
*original*, uncommitted 2026-09-20 set - this rebuilt set is not a like-for-like
comparison, see the plan's "Flagged assumptions".)

### google

```
Provider: google (gemini-3.1-flash-lite)
Score: 8/8
Titles/min: 100.7
JSON failures: 0
Score: 8/8
Titles/min: 100.4
JSON failures: 0
```

**Verdict: mistral 7/8, google 8/8; Success Criterion 5 met: no (mistral falls one
case short; google meets N/N).**

No bug was found in `scripts/benchmark_provider.py` itself during these runs, so no
change was made to it after Task 2 locked the case list.

## Full test suite

`PYTHONIOENCODING=utf-8 python -m pytest -q tests --ignore=tests/test_frontend_e2e.py`:
`381 passed, 3 failed` - all 3 failures are in `tests/test_settings.py` and
`tests/test_price_freshness.py`, files owned by other in-flight plans (ENV/settings
hardening and OPS-05 freshness), unrelated to this plan's files. `tests/test_benchmark_provider.py`
itself: `27 passed`.

## What's left / concerns

- The mistral miss above should go to the owner as a real (small) provider-accuracy
  finding, not something this plan can or should "fix" by editing the answer key.
- `scripts/benchmark_provider.py` is untracked (not committed) - the manager should
  commit `scripts/benchmark_provider.py` and `tests/test_benchmark_provider.py`.
- The dropped MSI MAG A650BN candidate surfaced a genuine 80 PLUS registry data
  inconsistency (two rows, identical model number, conflicting Silver/Bronze
  ratings) worth flagging to whoever maintains `data/raw/All_certified_psus.xlsx`
  imports, independent of this benchmark.

---

## Fix round 1 (architect review, applied on top of commit `10b9076`)

The architect's review found the case-3 answer-key entry above (Corsair RM750E,
locked as `80+ Gold`) was wrong: the title states only a Cybenetics rating, and per
the production prompt and the grounding rule, the correct extraction from *this
title* is `null`, even though the product's real 80 PLUS certification is
independently Gold. Full detail, all other fixes (evidence field corrections to
match the registry verbatim, MSI MAG A650BN re-locked as Bronze in place of dropping
it, two test fixes, docstring corrections, `--runs < 1` rejection), and the
post-fix live re-runs (mistral now 8/8, google now 7/8 - it leaks the Cybenetics-
adjacent Gold tier on the corrected case) are recorded in
`.superpowers/sdd/phase-01/plan-01-06-report.md`'s "Fix round 1" section - not
duplicated here to avoid the two documents drifting out of sync.

The case table above (rows locked/dropped) is otherwise unchanged by the fix round,
**except**: case 3's `expected` is now `None` (not `80+ Gold`), and MSI MAG A650BN
(650W) moved from "Dropped - registry itself is ambiguous" to **Locked** as
`80+ Bronze`, using its unambiguous `115V Internal` / `04/10/2013` row (the `230V EU
Internal` / `03/31/2023` Silver row is a documented later EU-certification uplift,
per PROGRESS.md's 2026-09-24 audit, not the retail tier). MSI MAG A850GL PCIE5 was
dropped in its place (redundant with the already-locked A750GL "GL"-suffix trap) to
hold the case count at 8.
