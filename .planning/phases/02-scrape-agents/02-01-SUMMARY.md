# 02-01 Summary: job queue, agent tokens, protocol

Worked inline (no agents), test-first. Requirements: AGENT-01, 02, 03, 04 (CLI and
storage side; endpoint 401s and per-token limits are 02-04), 05, 09 (columns; wiring the
save path is 02-02).

## What was built

- **Migration `b6d1e8f3a027`** (applied to the local DB; upgrade, downgrade, upgrade
  checked): `scrape_agents`, `scrape_jobs`, `pipeline_runs`; `stores.min_fetch_interval_s`
  (default 10 s) and `stores.next_fetch_at`; `price_history.agent_id` / `job_id`, nullable
  with no default so the 424k existing rows aren't rewritten, plus a partial index on
  `agent_id`. `alembic check` shows no drift for any of it.
- **`src/pipeline/job_queue.py`**: `enqueue`, `lease`, `complete`, `reap`, `status_counts`.
- **`src/pipeline/agent_tokens.py`** and **`scripts/agent_tokens.py create|list|revoke`**.
- **`docs/AGENT_PROTOCOL.md`**: the contract for 02-04 (endpoints) and 02-05 (extension).

## Decisions worth knowing

- **Pacing lives on the store row.** `next_fetch_at` is the store's next free fetch slot.
  A lease locks the store row (`SKIP LOCKED`), gives the job that slot as `not_before`,
  and moves the slot on by the interval. So the gap holds across all agents, and one
  lease call can hand out several jobs for a store with staggered start times inside a
  25 s window. The roadmap only named `min_fetch_interval_s`; `next_fetch_at` was added
  to make the shared budget enforceable.
- **Default interval 10 s.** Today's scraper has no pacing at all, so this is already
  gentler. Tune per store in `stores.min_fetch_interval_s`.
- **Exactly-once saves.** `complete()` takes a `process(job, upload)` callback that
  parses and saves inside the same transaction as the job's status change. 02-02 writes
  that callback. A repeat of the same `(job_id, lease_id)` returns the stored outcome,
  including after a retry re-queued the job.
- **Enqueue refuses** unknown job types, headers outside `Accept` / `X-Requested-With` /
  `HX-Request`, and any URL that isn't https on the store's own domain (subdomains allowed).
- **Inactive stores are never leased**, so PCStudio's jobs would just wait.
- Lease expiry counts from `not_before`, not from the lease call, so a job scheduled 20 s
  into the batch still gets its full 120 s.

## Tests

`tests/test_job_queue.py` (22) and `tests/test_agent_tokens.py` (7) run on a throwaway
Postgres schema (`scratch_engine` / `scratch_sessions` in `tests/conftest.py`), never the
live catalog. Includes 2 concurrent leasers x 200 jobs (no job twice) and 3 agents on 3
stores (no two starts for one store closer than the interval). Mutation check: removing
the row locks makes both concurrency tests fail.

## For later plans

- 02-02: write the `process` callback (validation, parse, save with `agent_id`/`job_id`).
- 02-03: the worker calls `reap()` on a schedule and writes `pipeline_runs`.
- 02-04: endpoints map `StaleLease` to 409; heartbeat sets `last_seen_at`.
