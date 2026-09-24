# 01-04 Summary: per-store freshness, backlog check, DB measurement

## Task 1 - Per-store freshness (OPS-05)

Added `stale_stores`, `format_stale_message`, `latest_price_by_store` at module level in
`dags/scheduled_scraper_dag.py`, outside the Airflow import guard. Rewrote
`check_price_freshness()` to use them; task wiring (`freshness_task`) unchanged.

Read-only smoke against the live DB:
```
10
{'Computech Store': 2026-09-24 22:00:04, 'TLG Gaming': 2026-09-24 20:00:10,
 'PCStudio': 2026-08-17 13:31:07, 'ModxComputers': 2026-09-24 20:00:05,
 'PrimeABGB': 2026-09-24 21:30:16, 'Vedant Computers': 2026-09-24 21:30:36,
 'EliteHubs': 2026-09-24 22:00:06, 'MDComputers': 2026-09-24 21:30:26,
 'Clarion Computers': 2026-09-24 20:30:19, 'TPS Tech': 2026-09-24 22:00:10}
```
10 active stores, matching the acceptance criterion. **Real finding**: PCStudio's last
saved price is 2026-08-17 - over a month stale. With this plan's change,
`check_price_freshness` will now fail on the next run naming "PCStudio (last:
2026-08-17 13:31:07.548120)" until either PCStudio starts saving prices again or is
deactivated. This is exactly the failure OPS-05 exists to surface; it is not something
this plan should silently work around.

## Task 2 - Loud failure on 0 extractions with a backlog (OPS-06)

Backlog measurement (read-only, `canonical_id IS NULL` across the 9 `BACKLOG_CATEGORIES`),
before writing the check:

```
TOTAL backlog (canonical_id IS NULL, all 9 categories): 0
```

Per-category/status breakdown ignoring the canonical_id filter (for context on where
`spec_status="pending"` products actually sit):

| Category      | extracted | needs_review | pending |
|---------------|-----------|--------------|---------|
| CPU           | 358       | 219          | 69      |
| CPU Cooler    | 180       | 1079         | 281     |
| Cabinet       | 1780      | 352          | 17      |
| GPU           | 1047      | 70           | 151     |
| Monitor       | 1192      | 103          | 184     |
| Motherboard   | 171       | 1421         | 281     |
| Power Supply  | 1016      | 41           | 10      |
| RAM           | 1183      | 2            | 144     |
| Storage       | 1274      | 72           | 121     |

**No permanent residue found**: at measurement time every product in these 9 categories
already has a `canonical_id`, including the `spec_status="pending"` rows (identity
extraction and physical-spec extraction are tracked separately - `canonical_id` is set
by identity extraction; `spec_status` reflects the later physical-spec stage). So there
is currently no group of rows that would keep `check_extraction_progress` firing every
cycle. This can change if a future title becomes permanently unparseable; no exclusion
rule is added pre-emptively since none is needed today, per the plan's instruction to
report numbers rather than silently pick a rule.

Added at module level, outside the guard: `BACKLOG_CATEGORIES`, `backlog_snapshot`,
`state_of`, `count_extraction_progress`, `check_extraction_progress`,
`execute_canonical_extraction_checked`. DAG wiring: `canonical_extraction_task` now uses
`python_callable=execute_canonical_extraction_checked`; `physical_specs_task` gets
`trigger_rule="all_done"` so it still runs on whatever is already keyed if extraction
fails loudly for provider exhaustion.

## Task 3 - Read-only DB size/growth measurement (OPS-07)

Dump measured by hand: `docker exec pc_builder_postgres pg_dump -Fc -U pc_builder
pc_builder | wc -c` = **10,988,023 bytes** (10.5 MB).

Full script output (`python scripts/measure_db_growth.py --dump-bytes 10988023`):
```
==============================================================================
DB SIZE AND GROWTH (read-only)
==============================================================================
Database size: 128.0 MB

Largest tables:
  price_history                       33.3 MB
  products                            14.5 MB
  cabinet_specs                       5.9 MB
  cabinet_title_extractions           5.7 MB
  motherboard_title_extractions       4.9 MB
  psu_title_extractions               4.8 MB
  products_backup                     4.3 MB
  motherboard_specs                   4.3 MB
  canonical_parts                     3.5 MB
  ram_title_extractions               3.5 MB

price_history: 402296 rows, 2026-07-27 20:04:52.944067 .. 2026-09-24 22:15:07.903204
  rows/day (last 7d avg):    4535.7
  rows/day (last 30d avg):   1058.3
  rows/day (whole-history avg, 59 days): 6808.1
  bytes/row: 86.8
  distinct products/day with a price (last 7d avg, rollup size): 1137.4

12-month projection (against the 150 GB block volume):
  keep everything:            333.8 MB - fits: True
  90 days raw + daily low/high: 204.7 MB - fits: True

Measured dump size (per copy, today): 10.5 MB
12-month projected dump size (per copy, keep-everything growth rate): 27.3 MB
  fits OCI Object Storage (20 GB) per copy: True
  fits R2 (10 GB) per copy: True
  (how many copies to retain is decided in 03-03)
==============================================================================
```

**Correction (fix round 1)**: the 30-day average (1,058 rows/day) is low because scraping
stalled for part of that window, not because of an "early, slower period" as originally
written here - that description was wrong and has been replaced. The script now also
prints the whole-history average (6,808 rows/day over the full 59-day span) and projects
from the highest of the 7-day, 30-day and whole-history rates (`forward_rate()` in
`scripts/measure_db_growth.py`), rather than just the higher of two. Here that is the
whole-history rate, 6,808 rows/day, higher than the 7-day figure used in the original
run.

**Plain-English answer: retention does NOT need to be applied in 03-03.** Keep-everything
growth over 12 months projects to ~333.8 MB against a 150 GB volume (0.2% used) and a
~27.3 MB compressed dump per copy against 20 GB / 10 GB free tiers (0.1-0.3% used), using
the corrected (higher, whole-history) rate. `price_history` retention is a non-issue at
this data volume; 03-03 can defer the rollup unless growth rate changes by orders of
magnitude.

## Fix round 1 (architect review)

- `pipeline_failed_guard` (trigger_rule="one_failed", downstream of every stage) now
  makes the DagRun's own state `failed` when any stage failed, even though every stage
  itself uses `trigger_rule="all_done"` so downstream stages keep working. **Phase 2
  worker must exit non-zero when any stage fails, not only the last.**
- `execute_canonical_extraction_checked`'s `limit_per_category` now defaults to `None`
  and falls back to 15 (matching `execute_canonical_extraction`'s own default) instead
  of silently cutting the DAG's no-argument call down to 10.
- `stale_stores` and `check_price_freshness` now compare in naive UTC throughout
  (`_as_naive_utc`), instead of blindly attaching one value's tzinfo to another (which
  changes the instant a naive value represents rather than converting it). A worker
  running in a non-UTC local time zone (e.g. IST) no longer flags every store stale
  hours early/late.
- Growth-rate projection now also considers the whole-history average and uses the
  highest of the three windows, since a short window being low can reflect a scraping
  stall rather than a genuinely slower period (see correction above).

## Files changed
- `dags/scheduled_scraper_dag.py`
- `tests/test_price_freshness.py`
- `scripts/measure_db_growth.py` (new)
- `tests/test_db_growth.py` (new)

## Test result
Original: `python -m pytest -q tests --ignore=tests/test_frontend_e2e.py`: **353 passed**.
Fix round 1: see `.superpowers/sdd/phase-01/plan-01-04-report.md` for the updated
RED/GREEN evidence and quick-suite result.
