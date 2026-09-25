r"""The scrape job queue that browser-extension agents pull work from (plan 02-01).

Life cycle of a job (docs/AGENT_PROTOCOL.md has the agent's side):

    queued --lease--> leased --complete--> done | blocked | rejected | failed
                        |                    \--(retry)--> queued, with backoff
                        \--lease expired, reap()--> queued with backoff, or failed
                                                    after MAX_ATTEMPTS leases

Every function here takes a session and commits (or rolls back) before returning, so
row locks are held only for the length of one call. Times are naive UTC, like the rest
of the schema; `now` can be passed in so tests don't have to sleep.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models.scrape_agent import ScrapeAgent
from db.models.scrape_job import JOB_STATUSES, JOB_TYPES, ScrapeJob
from db.models.store import Store

# The only request headers a job may ask an agent to send. Anything else (cookies,
# auth, a spoofed Referer...) is refused when the job is queued.
ALLOWED_HEADERS = frozenset({"Accept", "X-Requested-With", "HX-Request"})

LEASE_SECONDS = 120          # an agent has this long after a job's not_before to upload
LEASE_WINDOW_SECONDS = 25    # one lease call hands out only fetches due within this window
MAX_LEASE_BATCH = 50
MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 60      # backoff after the Nth failed attempt: 60 s * 2**(N-1)

# What a result processor may return, and what the job then becomes. "retry" (the
# agent's fetch failed: timeout, 5xx...) re-queues until the attempts run out.
PROCESS_STATUSES = ("done", "blocked", "rejected", "failed", "retry")


class StaleLease(Exception):
    """The upload doesn't match the job's current lease (HTTP 409 for the agent)."""


@dataclass(frozen=True)
class LeasedJob:
    job_id: int
    lease_id: str
    url: str
    headers: dict
    store_host: str
    not_before: datetime


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _host_belongs_to_store(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def enqueue(
    session,
    *,
    store_id: int,
    job_type: str,
    url: str,
    headers: dict | None = None,
    page: int | None = None,
    target_id: int | None = None,
    product_id: int | None = None,
    now: datetime | None = None,
) -> int | None:
    """Queue one page. Returns the new job id, or None if that page is already queued
    or being fetched for this store.

    Raises ValueError for an unknown job type, a header outside ALLOWED_HEADERS, or a
    URL that isn't https on the store's own domain - the queue never asks an agent to
    fetch anything else.
    """
    if job_type not in JOB_TYPES:
        raise ValueError(f"unknown job type {job_type!r}")
    headers = dict(headers or {})
    extra = sorted(set(headers) - ALLOWED_HEADERS)
    if extra:
        raise ValueError(f"headers not allowed: {', '.join(extra)}")
    store = session.get(Store, store_id)
    if store is None or not store.domain:
        raise ValueError(f"store {store_id} has no domain to check URLs against")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not _host_belongs_to_store(host, store.domain.lower()):
        raise ValueError(f"{url!r} is not an https URL on {store.domain}")

    stmt = (
        pg_insert(ScrapeJob)
        .values(
            store_id=store_id, job_type=job_type, url=url, headers=headers, page=page,
            target_id=target_id, product_id=product_id, status="queued",
            available_at=now or utcnow(),
        )
        .on_conflict_do_nothing(
            index_elements=["store_id", "url"],
            index_where=text("status IN ('queued', 'leased')"),
        )
        .returning(ScrapeJob.id)
    )
    job_id = session.execute(stmt).scalar_one_or_none()
    session.commit()
    return job_id


def lease(session, agent_id: int, max_jobs: int, now: datetime | None = None) -> list[LeasedJob]:
    """Hand an agent up to max_jobs fetches due within the next LEASE_WINDOW_SECONDS.

    Pacing is per store and shared by every agent: the store row is locked while its
    jobs are handed out, each job gets the store's next free slot as its not_before,
    and the slot moves on by min_fetch_interval_s. Stores and jobs are locked with
    SKIP LOCKED, so two agents leasing at once never wait on each other and never get
    the same job. Jobs are spread round-robin across stores. Also records the agent's
    heartbeat.
    """
    now = now or utcnow()
    max_jobs = max(0, min(int(max_jobs), MAX_LEASE_BATCH))
    horizon = now + timedelta(seconds=LEASE_WINDOW_SECONDS)

    agent = session.get(ScrapeAgent, agent_id)
    if agent is not None:
        agent.last_seen_at = now

    leased: list[LeasedJob] = []
    if max_jobs:
        has_due_job = (
            select(ScrapeJob.id)
            .where(
                ScrapeJob.store_id == Store.id,
                ScrapeJob.status == "queued",
                ScrapeJob.available_at <= now,
            )
            .exists()
        )
        stores = list(session.execute(
            select(Store)
            .where(
                Store.active.is_(True),
                or_(Store.next_fetch_at.is_(None), Store.next_fetch_at <= horizon),
                has_due_job,
            )
            .order_by(Store.next_fetch_at.asc().nulls_first(), Store.id)
            .limit(max_jobs)
            .with_for_update(skip_locked=True, of=Store)
            .execution_options(populate_existing=True)
        ).scalars())

        while stores and len(leased) < max_jobs:
            for store in list(stores):
                if len(leased) >= max_jobs:
                    break
                slot = max(now, store.next_fetch_at or now)
                job = None
                if slot <= horizon:
                    job = session.execute(
                        select(ScrapeJob)
                        .where(
                            ScrapeJob.store_id == store.id,
                            ScrapeJob.status == "queued",
                            ScrapeJob.available_at <= now,
                        )
                        .order_by(ScrapeJob.available_at, ScrapeJob.id)
                        .limit(1)
                        .with_for_update(skip_locked=True)
                        .execution_options(populate_existing=True)
                    ).scalar_one_or_none()
                if job is None:
                    stores.remove(store)
                    continue
                job.status = "leased"
                job.lease_id = str(uuid4())
                job.agent_id = agent_id
                job.attempts += 1
                job.not_before = slot
                job.lease_expires_at = slot + timedelta(seconds=LEASE_SECONDS)
                store.next_fetch_at = slot + timedelta(seconds=store.min_fetch_interval_s)
                session.flush()  # so the next pick for this store doesn't see it as queued
                leased.append(LeasedJob(
                    job_id=job.id,
                    lease_id=job.lease_id,
                    url=job.url,
                    headers=dict(job.headers or {}),
                    store_host=urlsplit(job.url).hostname,
                    not_before=slot,
                ))
    session.commit()
    return leased


def _clear_lease(job: ScrapeJob) -> None:
    job.lease_id = None
    job.lease_expires_at = None


def _requeue(job: ScrapeJob, now: datetime, reason: str | None) -> None:
    job.status = "queued"
    job.available_at = now + timedelta(seconds=RETRY_BASE_SECONDS * 2 ** max(job.attempts - 1, 0))
    job.agent_id = None
    job.not_before = None
    job.reason = reason
    _clear_lease(job)


def complete(session, job_id: int, lease_id: str, agent_id: int, upload, process, now: datetime | None = None) -> dict:
    """Take an agent's upload for a leased job, exactly once.

    `process(job, upload)` validates, parses and saves, inside this transaction, and
    returns {"status": one of PROCESS_STATUSES, "reason": ..., any counts}. It must not
    commit. The saves and the job's new status commit together, so a job's prices are
    saved once or not at all. If it raises, nothing is saved and the lease is left to
    expire (and be retried).

    The same (job_id, lease_id) again returns the stored outcome without calling
    process. Any other lease, agent or job raises StaleLease and saves nothing.
    """
    now = now or utcnow()
    job = session.execute(
        select(ScrapeJob)
        .where(ScrapeJob.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()

    if job is not None and lease_id and job.result_lease_id == lease_id and job.outcome is not None:
        outcome = dict(job.outcome)
        session.rollback()
        return outcome
    if job is None or job.status != "leased" or job.lease_id != lease_id or job.agent_id != agent_id:
        session.rollback()
        raise StaleLease(f"job {job_id}: lease {lease_id!r} is not current")

    try:
        result = dict(process(job, upload))
        status = result.get("status")
        if status not in PROCESS_STATUSES:
            raise ValueError(f"result processor returned status {status!r}")
    except BaseException:
        session.rollback()
        raise

    reason = result.get("reason")
    if status == "retry":
        status = "failed" if job.attempts >= MAX_ATTEMPTS else "requeued"
    outcome = {**result, "status": status}

    job.result_lease_id = lease_id
    job.outcome = outcome
    if status == "requeued":
        _requeue(job, now, reason)
    else:
        job.status = status
        job.reason = reason
        job.finished_at = now
        _clear_lease(job)
    session.commit()
    return outcome


def reap(session, now: datetime | None = None) -> dict:
    """Return expired leases to the queue with backoff, or fail them after
    MAX_ATTEMPTS. Returns {"requeued": n, "failed": n}."""
    now = now or utcnow()
    expired = session.execute(
        select(ScrapeJob)
        .where(ScrapeJob.status == "leased", ScrapeJob.lease_expires_at < now)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).scalars().all()
    counts = {"requeued": 0, "failed": 0}
    for job in expired:
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "failed"
            job.reason = f"lease expired on all {job.attempts} attempts"
            job.finished_at = now
            _clear_lease(job)
            counts["failed"] += 1
        else:
            _requeue(job, now, "lease expired")
            counts["requeued"] += 1
    session.commit()
    return counts


def status_counts(session) -> dict:
    """Jobs per status, every status present (0 if none). For health checks."""
    counts = dict.fromkeys(JOB_STATUSES, 0)
    counts.update(dict(session.execute(
        select(ScrapeJob.status, func.count()).group_by(ScrapeJob.status)
    ).all()))
    session.rollback()
    return counts
