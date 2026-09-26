"""What /health/pipeline checks (AGENT-12).

The pipeline is unhealthy when any of these holds:
- no agent has checked in for AGENT_SILENCE (every extension off, or every token revoked)
- no price has been saved for PRICE_SILENCE (agents run but nothing lands)
- a scheduled worker task's latest run failed, or it hasn't started for more than two
  of its intervals. Only tasks that have run at least once are checked, so a setup
  where Airflow still does the work (local development) isn't reported as broken.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select

from db.models.pipeline_run import PipelineRun
from db.models.price_history import PriceHistory
from db.models.scrape_agent import ScrapeAgent
from pipeline.job_queue import status_counts, utcnow
from pipeline.schedule import TASK_INTERVALS

AGENT_SILENCE = timedelta(hours=24)
PRICE_SILENCE = timedelta(hours=24)

# task name -> how often it runs: the worker's tasks (plan 02-03), plus the nightly
# database backup, which a systemd timer on the VM runs (scripts/backup_db.sh, 03-03).
SCHEDULED_TASKS: dict[str, timedelta] = {**TASK_INTERVALS, "db_backup": timedelta(days=1)}


def pipeline_problems(session, now: datetime | None = None) -> list[str]:
    now = now or utcnow()
    problems = []

    last_agent = session.execute(
        select(func.max(ScrapeAgent.last_seen_at)).where(ScrapeAgent.revoked_at.is_(None))
    ).scalar_one()
    if last_agent is None or now - last_agent > AGENT_SILENCE:
        problems.append(f"no agent has checked in since {last_agent or 'ever'}")

    last_price = session.execute(select(func.max(PriceHistory.scraped_at))).scalar_one()
    if last_price is None or now - last_price > PRICE_SILENCE:
        problems.append(f"no price saved since {last_price or 'ever'}")

    for task, interval in SCHEDULED_TASKS.items():
        latest = session.execute(
            select(PipelineRun).where(PipelineRun.task == task).order_by(PipelineRun.started_at.desc()).limit(1)
        ).scalar_one_or_none()
        if latest is None:
            continue  # never run here: this setup doesn't use the worker for it
        if latest.status == "failed":
            problems.append(f"task {task} failed at {latest.started_at}: {(latest.error or '')[:200]}")
        if now - latest.started_at > 2 * interval:
            problems.append(f"task {task} is overdue: last started {latest.started_at}")
    return problems


def pipeline_report(session, now: datetime | None = None) -> dict:
    problems = pipeline_problems(session, now)
    return {"status": "fail" if problems else "ok", "problems": problems, "jobs": status_counts(session)}
