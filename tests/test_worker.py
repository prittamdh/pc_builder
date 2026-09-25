"""The worker that replaces Airflow (plan 02-03, AGENT-11).

Uses the throwaway schema: `worker.SessionLocal` is pointed at it, and the heavy
stages (LLM extraction etc.) are swapped for fakes - what's under test is the
scheduling, the recording in pipeline_runs, and that one failure doesn't stop the rest.
"""
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from db.models.pipeline_run import PipelineRun
from pipeline import schedule, worker

ROOT = Path(__file__).resolve().parent.parent
T0 = datetime(2026, 10, 1, 12, 0, 0)


@pytest.fixture
def db(scratch_sessions, monkeypatch):
    monkeypatch.setattr(worker, "SessionLocal", scratch_sessions)
    return scratch_sessions


def runs(db):
    with db() as s:
        return [(r.task, r.status) for r in s.execute(select(PipelineRun).order_by(PipelineRun.id)).scalars()]


def fake_units(calls, fail=()):
    def step(name):
        def fn():
            calls.append(name)
            if name in fail:
                raise RuntimeError(f"{name} broke")
            return {"did": name}
        return worker.Step(name, fn)

    return [
        worker.Unit("reap", timedelta(minutes=1), [step("reap")]),
        worker.Unit("catalog", timedelta(minutes=15), [step("canonical_extraction"), step("physical_specs"), step("catalog_policy")]),
        worker.Unit("price_freshness", timedelta(hours=1), [step("price_freshness")]),
    ]


def test_a_run_is_recorded_with_its_counts(db):
    worker.run_step(worker.Step("reap", lambda: {"requeued": 2, "failed": 0}), started_at=T0)
    with db() as s:
        run = s.execute(select(PipelineRun)).scalar_one()
    assert (run.task, run.status, run.counts, run.started_at) == ("reap", "ok", {"requeued": 2, "failed": 0}, T0)
    assert run.finished_at is not None
    assert run.error is None


def test_a_failed_run_is_recorded_and_re_raised(db):
    def boom():
        raise ValueError("provider down")

    with pytest.raises(ValueError):
        worker.run_step(worker.Step("canonical_extraction", boom))
    with db() as s:
        run = s.execute(select(PipelineRun)).scalar_one()
    assert run.status == "failed"
    assert "provider down" in run.error
    assert "Traceback" in run.error


def test_one_failed_stage_does_not_stop_the_others(db):
    calls = []
    units = fake_units(calls, fail={"canonical_extraction"})
    ok = worker.run_due(units, last_started={}, now=T0)
    assert ok is False
    assert calls == ["reap", "canonical_extraction", "physical_specs", "catalog_policy", "price_freshness"]
    assert ("canonical_extraction", "failed") in runs(db)
    assert ("catalog_policy", "ok") in runs(db)


def test_only_due_units_run(db):
    calls = []
    units = fake_units(calls)
    last = {}
    worker.run_due(units, last, now=T0)
    calls.clear()
    worker.run_due(units, last, now=T0 + timedelta(minutes=2))
    assert calls == ["reap"]
    calls.clear()
    worker.run_due(units, last, now=T0 + timedelta(minutes=15))
    assert calls == ["reap", "canonical_extraction", "physical_specs", "catalog_policy"]


def test_a_restart_keeps_the_schedule(db):
    calls = []
    units = fake_units(calls)
    worker.run_due(units, {}, now=T0)
    last = worker.last_starts(units)
    calls.clear()
    worker.run_due(units, last, now=T0 + timedelta(minutes=5))
    assert calls == ["reap"]


def test_queueing_is_skipped_unless_agent_mode_is_on(db, monkeypatch):
    from configs import settings

    called = []
    monkeypatch.setattr(worker, "enqueue_due_targets", lambda s: called.append(1) or 4)
    monkeypatch.setattr(settings, "SCRAPE_VIA_AGENTS", False)
    assert worker.queue_for_agents() == {"skipped": "SCRAPE_VIA_AGENTS is off"}
    assert called == []
    monkeypatch.setattr(settings, "SCRAPE_VIA_AGENTS", True)
    assert worker.queue_for_agents() == {"queued": 4}


def test_the_real_schedule_covers_every_task_health_watches():
    names = {step.name for unit in worker.UNITS for step in unit.steps}
    assert names == set(schedule.TASK_INTERVALS)
    for unit in worker.UNITS:
        for step in unit.steps:
            assert schedule.TASK_INTERVALS[step.name] == unit.every
    # the catalog stages run in this order (identities key specs; policy reads specs)
    catalog = next(u for u in worker.UNITS if len(u.steps) > 1)
    assert [s.name for s in catalog.steps] == ["canonical_extraction", "physical_specs", "catalog_policy"]


def test_the_worker_never_imports_from_dags():
    for name in ("worker.py", "tasks.py", "checks.py"):
        src = (ROOT / "src" / "pipeline" / name).read_text(encoding="utf-8")
        imports = [ln for ln in src.splitlines() if ln.lstrip().startswith(("import ", "from "))]
        assert not [ln for ln in imports if "dag" in ln], imports


def test_once_exits_non_zero_when_a_stage_failed(db, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "UNITS", fake_units(calls, fail={"price_freshness"}))
    assert worker.main(["--once"]) == 1
    calls.clear()
    monkeypatch.setattr(worker, "UNITS", fake_units(calls))
    assert worker.main(["--once"]) == 0


def test_cli_help():
    out = subprocess.run(
        [sys.executable, "-m", "pipeline.worker", "--help"],
        capture_output=True, text=True, encoding="utf-8", check=True, cwd=ROOT / "src",
    ).stdout
    assert "--once" in out
