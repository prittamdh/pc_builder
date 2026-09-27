"""The pipeline worker: replaces Airflow in production (plan 02-03, AGENT-11).

One plain process that, on a schedule (pipeline/schedule.py):

    every minute     reap          expired agent leases go back in the queue
    every 5 minutes  queue         page 1 of due targets, for the extensions
                                   (only when SCRAPE_VIA_AGENTS is on)
    every 15 minutes catalog       identity extraction -> physical specs ->
                                   catalog policy, in that order
    every hour       freshness     fail, naming the store, when a store stopped saving

Every step is one row in pipeline_runs (task, start, end, status, counts, error), which
/health/pipeline reads. A failed step is recorded with its traceback and re-raised; the
loop logs it and carries on with the other steps, so one broken stage never stalls the
rest. `--once` runs everything once and exits 1 if any step failed.

    python -m pipeline.worker            # run forever (the compose `worker` service)
    python -m pipeline.worker --once     # one pass, e.g. from cron or by hand
"""
import argparse
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import func, select

from configs import settings
from db.models.pipeline_run import PipelineRun
from db.session import SessionLocal
from pipeline import job_queue
from pipeline.checks import check_price_freshness
from pipeline.identity_audit import check_identity_sizes
from pipeline.scrape_planning import enqueue_due_targets
from pipeline.schedule import TASK_INTERVALS
from pipeline.tasks import (
    execute_canonical_extraction_checked,
    execute_catalog_policy,
    execute_physical_spec_extraction,
)

POLL_SECONDS = 15


@dataclass(frozen=True)
class Step:
    name: str
    fn: Callable[[], object]


@dataclass(frozen=True)
class Unit:
    """Steps that run together, in order, whenever the unit is due."""
    name: str
    every: timedelta
    steps: list = field(default_factory=list)


def reap_leases():
    with SessionLocal() as s:
        return job_queue.reap(s)


def queue_for_agents():
    # Off, Airflow's own scraper is still fetching from this machine; queueing too would
    # take its due targets away from it.
    if not settings.SCRAPE_VIA_AGENTS:
        return {"skipped": "SCRAPE_VIA_AGENTS is off"}
    with SessionLocal() as s:
        return {"queued": enqueue_due_targets(s)}


def _every(name: str) -> timedelta:
    return TASK_INTERVALS[name]


UNITS = [
    Unit("reap", _every("reap"), [Step("reap", reap_leases)]),
    Unit("enqueue_due_targets", _every("enqueue_due_targets"), [Step("enqueue_due_targets", queue_for_agents)]),
    Unit("catalog", _every("canonical_extraction"), [
        Step("canonical_extraction", execute_canonical_extraction_checked),
        Step("physical_specs", execute_physical_spec_extraction),
        Step("catalog_policy", execute_catalog_policy),
    ]),
    Unit("price_freshness", _every("price_freshness"), [Step("price_freshness", check_price_freshness)]),
    Unit("identity_audit", _every("identity_audit"), [Step("identity_audit", check_identity_sizes)]),
]


def run_step(step: Step, started_at: datetime | None = None):
    """Run one step and record it in pipeline_runs. Re-raises the step's exception
    after recording it. started_at is the scheduled pass's time (what the schedule and
    /health/pipeline go by); finished_at is the real clock."""
    started_at = started_at or job_queue.utcnow()
    with SessionLocal() as s:
        run = PipelineRun(task=step.name, started_at=started_at, status="running")
        s.add(run)
        s.commit()
        run_id = run.id

    status, counts, error = "ok", None, None
    try:
        result = step.fn()
        counts = result if isinstance(result, dict) else None
    except Exception:
        status, error = "failed", traceback.format_exc()[-4000:]
        raise
    finally:
        with SessionLocal() as s:
            run = s.get(PipelineRun, run_id)
            run.status, run.counts, run.error = status, counts, error
            run.finished_at = max(started_at, job_queue.utcnow())
            s.commit()


def run_due(units, last_started: dict, now: datetime | None = None) -> bool:
    """Run every unit that is due. Returns False if any step failed."""
    now = now or job_queue.utcnow()
    all_ok = True
    for unit in units:
        last = last_started.get(unit.name)
        if last is not None and now - last < unit.every:
            continue
        last_started[unit.name] = now
        for step in unit.steps:
            try:
                run_step(step, started_at=now)
                print(f"[worker] {step.name}: ok", flush=True)
            except Exception as exc:
                all_ok = False
                print(f"[worker] {step.name}: FAILED - {type(exc).__name__}: {exc}", flush=True)
    return all_ok


def last_starts(units) -> dict:
    """Each unit's last start from pipeline_runs, so a restart keeps the schedule
    instead of re-running everything at once."""
    firsts = {unit.steps[0].name: unit.name for unit in units}
    with SessionLocal() as s:
        rows = s.execute(
            select(PipelineRun.task, func.max(PipelineRun.started_at))
            .where(PipelineRun.task.in_(firsts))
            .group_by(PipelineRun.task)
        ).all()
    return {firsts[task]: started for task, started in rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.worker", description="Run the pipeline's scheduled tasks.")
    parser.add_argument("--once", action="store_true", help="run every task once, exit 1 if any failed")
    args = parser.parse_args(argv)

    if args.once:
        return 0 if run_due(UNITS, {}) else 1

    print(f"[worker] started; SCRAPE_VIA_AGENTS={settings.SCRAPE_VIA_AGENTS}", flush=True)
    last = last_starts(UNITS)
    try:
        while True:
            run_due(UNITS, last)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("[worker] stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
