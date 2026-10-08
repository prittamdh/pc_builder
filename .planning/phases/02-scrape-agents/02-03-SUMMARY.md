# 02-03 Summary: the worker that replaces Airflow

Worked inline, test-first. Requirement: AGENT-11 (and the 02-03 carry-forwards from
Phase 1).

## What was built

- **`src/pipeline/checks.py`** and **`src/pipeline/tasks.py`**: the freshness and
  backlog checks and the three catalog stages, moved word for word out of
  `dags/scheduled_scraper_dag.py`. The DAG imports them from there, so Airflow runs the
  same code; the worker never imports from `dags/`.
- **`src/pipeline/worker.py`** (`python -m pipeline.worker [--once]`): runs, on the
  schedule in `src/pipeline/schedule.py`:

  | Every | Unit | Steps |
  |-------|------|-------|
  | 1 min | reap | expired leases back to the queue |
  | 5 min | queue | page 1 of due targets for the agents, only with `SCRAPE_VIA_AGENTS=true` |
  | 15 min | catalog | canonical extraction -> physical specs -> catalog policy, in order |
  | 1 h | freshness | per-store price freshness |

  Each step is a `pipeline_runs` row (task, start, end, status, counts, traceback). A
  failed step is recorded and re-raised; the loop logs it and runs the other steps.
  `--once` exits 1 if any step failed (the worker's version of `pipeline_failed_guard`).
  A restart reads the last start times from `pipeline_runs` and keeps the schedule.
- **`/health/pipeline`** now watches these intervals, but only for tasks that have run
  at least once, so a machine where Airflow still does the work isn't reported broken.
- **`worker` service in `docker-compose.yml`**, opt-in (`--profile worker`) so it never
  runs next to local Airflow by accident. Phase 3 (03-02) gives it a real image.

## Verified on real data

`--once` on the host and in the compose container: all six steps ok against the local
database (the queue step skipped, as `SCRAPE_VIA_AGENTS` is off). The test rows were
deleted afterwards so local health doesn't watch a worker that isn't running.

## Incident found while verifying (fixed in 2eb4248)

The three models from 02-01 imported `mapped_column` straight from `sqlalchemy.orm`.
The Airflow image has SQLAlchemy 1.4, so the DAG failed to import and **server-side
scraping stopped from about 17:00 to 22:00 IST on 2026-09-25**. Nothing failed loudly,
because no task ran at all. Fixed with the fallback the older models use, plus
`tests/test_models_airflow_compat.py`. A manual run in the Airflow container then saved
980 prices. Lesson: after a model change, check the DAG imports inside the Airflow
container (`airflow dags list-import-errors`).

## Carry-forward checks

- Backlog check going permanently red: extractors select with no ORDER BY, but a
  successful extraction always sets `canonical_id`; a row stays in the backlog only if
  its batch errors, which also marks it `failed`. A cycle is red only when no category
  makes progress. Acceptable; not changed.

## Noted

EliteHubs motherboards and cabinets each hit exactly 1,000 products (10 pages x 100) on
the Airflow run, so they may have more. Raise their `max_pages` if the catalog shows gaps.

## Tests

`tests/test_worker.py` (10); `tests/test_price_freshness.py` repointed at the new
modules (24, unchanged otherwise); `tests/test_models_airflow_compat.py`.
