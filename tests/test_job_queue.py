"""The scrape job queue (plan 02-01, AGENT-01/02/03/05).

Runs against a throwaway Postgres schema (see `scratch_sessions` in conftest), because
what matters here - row locks, SKIP LOCKED, the partial unique index - only exists in
Postgres.
"""
import threading
from datetime import datetime, timedelta

import pytest

from db.models.scrape_job import ScrapeJob
from db.models.store import Store
from pipeline import agent_tokens, job_queue
from pipeline.job_queue import StaleLease

# A day ahead of the real clock, never a fixed date: jobs enqueued without a time get
# the real "now", and a fixed T0 that slips into the past makes every lease at T0 find
# nothing (it did on 2026-10-06, when T0 was 2026-10-01).
T0 = (datetime.utcnow() + timedelta(days=1)).replace(second=0, microsecond=0)


def _store(session, name="mdcomputers", domain="mdcomputers.in", interval=10, active=True):
    store = Store(
        name=name, display_name=name, domain=domain, base_url=f"https://{domain}",
        search_endpoint="/", active=active, min_fetch_interval_s=interval,
    )
    session.add(store)
    session.commit()
    return store


def _agent(session, name="laptop"):
    agent, _token = agent_tokens.create_agent(session, name)
    return agent


def _enqueue_pages(session, store, n, host=None):
    host = host or store.domain
    return [
        job_queue.enqueue(
            session, store_id=store.id, job_type="category_page",
            url=f"https://{host}/cpu?page={i}", page=i,
        )
        for i in range(1, n + 1)
    ]


def _done(job, upload):
    return {"status": "done", "reason": None, "saved": 3}


# --- enqueue -------------------------------------------------------------------------


def test_enqueue_skips_a_url_already_queued_for_the_store(scratch_sessions):
    with scratch_sessions() as s:
        store = _store(s)
        first = job_queue.enqueue(s, store_id=store.id, job_type="category_page", url="https://mdcomputers.in/cpu")
        again = job_queue.enqueue(s, store_id=store.id, job_type="category_page", url="https://mdcomputers.in/cpu")
    assert first is not None
    assert again is None


def test_enqueue_refuses_a_header_outside_the_allowlist(scratch_sessions):
    with scratch_sessions() as s:
        store = _store(s)
        with pytest.raises(ValueError, match="Cookie"):
            job_queue.enqueue(
                s, store_id=store.id, job_type="category_page",
                url="https://mdcomputers.in/cpu", headers={"Cookie": "a=b"},
            )
        job_queue.enqueue(
            s, store_id=store.id, job_type="category_page",
            url="https://mdcomputers.in/x", headers={"HX-Request": "true", "Accept": "text/html"},
        )


def test_enqueue_refuses_a_url_off_the_store_host(scratch_sessions):
    with scratch_sessions() as s:
        store = _store(s, domain="vedantcomputers.com")
        for url in ("https://evil.example/cpu", "https://vedantcomputers.com.evil.example/",
                    "http://www.vedantcomputers.com/cpu", "https://10.0.0.1/"):
            with pytest.raises(ValueError):
                job_queue.enqueue(s, store_id=store.id, job_type="category_page", url=url)
        # the www. host of the store's domain is the store
        assert job_queue.enqueue(
            s, store_id=store.id, job_type="category_page", url="https://www.vedantcomputers.com/cpu",
        )


def test_enqueue_refuses_an_unknown_job_type(scratch_sessions):
    with scratch_sessions() as s:
        store = _store(s)
        with pytest.raises(ValueError):
            job_queue.enqueue(s, store_id=store.id, job_type="search", url="https://mdcomputers.in/")


# --- lease ---------------------------------------------------------------------------


def test_lease_returns_the_protocol_fields_and_records_a_heartbeat(scratch_sessions):
    with scratch_sessions() as s:
        store = _store(s)
        agent = _agent(s)
        (job_id,) = _enqueue_pages(s, store, 1)
        leased = job_queue.lease(s, agent.id, max_jobs=5, now=T0)
        s.refresh(agent)
        job = s.get(ScrapeJob, job_id)
    assert len(leased) == 1
    got = leased[0]
    assert got.job_id == job_id
    assert got.url == "https://mdcomputers.in/cpu?page=1"
    assert got.store_host == "mdcomputers.in"
    assert got.not_before == T0
    assert got.lease_id
    assert agent.last_seen_at == T0
    assert job.status == "leased"
    assert job.attempts == 1
    assert job.agent_id == agent.id
    assert job.lease_expires_at == T0 + timedelta(seconds=job_queue.LEASE_SECONDS)


def test_lease_skips_inactive_stores(scratch_sessions):
    with scratch_sessions() as s:
        store = _store(s, name="pcstudio", domain="pcstudio.in", active=False)
        agent = _agent(s)
        _enqueue_pages(s, store, 2)
        assert job_queue.lease(s, agent.id, max_jobs=5, now=T0) == []


def test_lease_spaces_one_stores_jobs_by_its_interval_within_the_window(scratch_sessions):
    with scratch_sessions() as s:
        store = _store(s, interval=10)
        agent = _agent(s)
        _enqueue_pages(s, store, 6)
        leased = job_queue.lease(s, agent.id, max_jobs=10, now=T0)
    starts = [j.not_before for j in leased]
    # 25 s window, 10 s interval: slots at +0, +10, +20
    assert starts == [T0, T0 + timedelta(seconds=10), T0 + timedelta(seconds=20)]


def test_lease_spreads_a_small_batch_across_stores(scratch_sessions):
    with scratch_sessions() as s:
        a = _store(s, name="a", domain="a.example.in")
        b = _store(s, name="b", domain="b.example.in")
        agent = _agent(s)
        _enqueue_pages(s, a, 5)
        _enqueue_pages(s, b, 5)
        leased = job_queue.lease(s, agent.id, max_jobs=2, now=T0)
    assert sorted(j.store_host for j in leased) == ["a.example.in", "b.example.in"]


def test_two_concurrent_leasers_never_get_the_same_job(scratch_sessions):
    """AGENT-01: 2 leasers hammering the queue at once never share a job."""
    with scratch_sessions() as s:
        agents = [_agent(s, "one").id, _agent(s, "two").id]
        for i in range(8):
            store = _store(s, name=f"s{i}", domain=f"s{i}.example.in", interval=0)
            _enqueue_pages(s, store, 25)

    got = {a: [] for a in agents}
    errors = []
    barrier = threading.Barrier(len(agents))

    def run(agent_id):
        try:
            barrier.wait()
            with scratch_sessions() as s:
                for _ in range(40):
                    got[agent_id].extend(j.job_id for j in job_queue.lease(s, agent_id, max_jobs=5))
        except Exception as exc:  # surfaced below; a thread's exception is otherwise lost
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(a,)) for a in agents]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    all_ids = got[agents[0]] + got[agents[1]]
    assert len(all_ids) == 200
    assert len(set(all_ids)) == len(all_ids)
    assert got[agents[0]] and got[agents[1]]


def test_three_agents_never_fetch_one_store_closer_than_its_interval(scratch_sessions):
    """AGENT-05: the interval holds across all agents together, not per agent."""
    interval = 7
    with scratch_sessions() as s:
        agents = [_agent(s, n).id for n in ("one", "two", "three")]
        stores = [_store(s, name=f"s{i}", domain=f"s{i}.example.in", interval=interval) for i in range(3)]
        for store in stores:
            _enqueue_pages(s, store, 30)

    starts = {}
    errors = []
    barrier = threading.Barrier(len(agents))

    def run(agent_id):
        try:
            barrier.wait()
            with scratch_sessions() as s:
                for step in range(20):
                    now = T0 + timedelta(seconds=5 * step)
                    for j in job_queue.lease(s, agent_id, max_jobs=4, now=now):
                        starts.setdefault(j.store_host, []).append(j.not_before)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(a,)) for a in agents]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert sum(len(v) for v in starts.values()) >= 30
    for host, times in starts.items():
        times.sort()
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        assert min(gaps) >= interval, (host, gaps)


# --- reaper --------------------------------------------------------------------------


def test_reaper_requeues_an_expired_lease_with_backoff(scratch_sessions):
    with scratch_sessions() as s:
        store = _store(s)
        agent = _agent(s)
        (job_id,) = _enqueue_pages(s, store, 1)
        job_queue.lease(s, agent.id, max_jobs=1, now=T0)

        still_live = T0 + timedelta(seconds=job_queue.LEASE_SECONDS - 1)
        assert job_queue.reap(s, now=still_live) == {"requeued": 0, "failed": 0}

        expired = T0 + timedelta(seconds=job_queue.LEASE_SECONDS + 1)
        assert job_queue.reap(s, now=expired) == {"requeued": 1, "failed": 0}
        job = s.get(ScrapeJob, job_id)
        assert job.status == "queued"
        assert job.lease_id is None
        assert job.agent_id is None
        assert job.available_at == expired + timedelta(seconds=job_queue.RETRY_BASE_SECONDS)

        # not handed out again until the backoff passes
        assert job_queue.lease(s, agent.id, max_jobs=1, now=expired + timedelta(seconds=30)) == []
        again = job_queue.lease(s, agent.id, max_jobs=1, now=job.available_at)
        assert [j.job_id for j in again] == [job_id]


def test_a_job_fails_after_three_expired_leases(scratch_sessions):
    """AGENT-02: after 3 attempts the job is `failed` and counted."""
    with scratch_sessions() as s:
        store = _store(s, interval=0)
        agent = _agent(s)
        (job_id,) = _enqueue_pages(s, store, 1)
        now = T0
        for attempt in range(1, job_queue.MAX_ATTEMPTS + 1):
            leased = job_queue.lease(s, agent.id, max_jobs=1, now=now)
            assert [j.job_id for j in leased] == [job_id], attempt
            now += timedelta(seconds=job_queue.LEASE_SECONDS + 1)
            job_queue.reap(s, now=now)
            now += timedelta(hours=1)
        job = s.get(ScrapeJob, job_id)
        assert job.status == "failed"
        assert job.attempts == job_queue.MAX_ATTEMPTS
        assert "lease expired" in job.reason
        assert job_queue.status_counts(s)["failed"] == 1
        assert job_queue.lease(s, agent.id, max_jobs=1, now=now) == []


# --- complete ------------------------------------------------------------------------


def _leased_job(s, interval=10):
    store = _store(s, interval=interval)
    agent = _agent(s)
    _enqueue_pages(s, store, 1)
    (leased,) = job_queue.lease(s, agent.id, max_jobs=1, now=T0)
    return agent, leased


def test_complete_runs_the_processor_once_and_replays_the_stored_outcome(scratch_sessions):
    """AGENT-03: the same (job_id, lease_id) again returns the first outcome, no re-save."""
    calls = []

    def process(job, upload):
        calls.append(job.id)
        return {"status": "done", "reason": None, "saved": 3}

    with scratch_sessions() as s:
        agent, leased = _leased_job(s)
        first = job_queue.complete(s, leased.job_id, leased.lease_id, agent.id, {"body": "x"}, process, now=T0)
        second = job_queue.complete(s, leased.job_id, leased.lease_id, agent.id, {"body": "x"}, process, now=T0)
        job = s.get(ScrapeJob, leased.job_id)
    assert calls == [leased.job_id]
    assert first == second
    assert first["status"] == "done"
    assert first["saved"] == 3
    assert job.status == "done"
    assert job.finished_at == T0


def test_complete_with_a_wrong_lease_saves_nothing(scratch_sessions):
    calls = []

    def process(job, upload):
        calls.append(job.id)
        return {"status": "done"}

    with scratch_sessions() as s:
        agent, leased = _leased_job(s)
        other = _agent(s, "desktop")
        with pytest.raises(StaleLease):
            job_queue.complete(s, leased.job_id, "not-the-lease", agent.id, {}, process, now=T0)
        with pytest.raises(StaleLease):  # right lease, wrong agent
            job_queue.complete(s, leased.job_id, leased.lease_id, other.id, {}, process, now=T0)
        with pytest.raises(StaleLease):
            job_queue.complete(s, 999_999, leased.lease_id, agent.id, {}, process, now=T0)
        assert s.get(ScrapeJob, leased.job_id).status == "leased"
    assert calls == []


def test_complete_after_the_lease_was_reaped_is_stale(scratch_sessions):
    with scratch_sessions() as s:
        agent, leased = _leased_job(s)
        job_queue.reap(s, now=T0 + timedelta(seconds=job_queue.LEASE_SECONDS + 1))
        with pytest.raises(StaleLease):
            job_queue.complete(s, leased.job_id, leased.lease_id, agent.id, {}, _done, now=T0)


def test_a_processor_error_saves_nothing_and_leaves_the_lease_to_expire(scratch_sessions):
    def process(job, upload):
        raise RuntimeError("parser blew up")

    with scratch_sessions() as s:
        agent, leased = _leased_job(s)
        with pytest.raises(RuntimeError):
            job_queue.complete(s, leased.job_id, leased.lease_id, agent.id, {}, process, now=T0)
        job = s.get(ScrapeJob, leased.job_id)
        assert job.status == "leased"
        assert job.outcome is None


def test_a_retry_outcome_requeues_until_attempts_run_out(scratch_sessions):
    def retry(job, upload):
        return {"status": "retry", "reason": "fetch error: timeout"}

    with scratch_sessions() as s:
        agent, leased = _leased_job(s, interval=0)
        out = job_queue.complete(s, leased.job_id, leased.lease_id, agent.id, {}, retry, now=T0)
        assert out["status"] == "requeued"
        job = s.get(ScrapeJob, leased.job_id)
        assert job.status == "queued"
        assert job.available_at == T0 + timedelta(seconds=job_queue.RETRY_BASE_SECONDS)
        # the old lease still replays its outcome after the requeue
        assert job_queue.complete(s, leased.job_id, leased.lease_id, agent.id, {}, retry, now=T0) == out

        now = T0
        for _ in range(job_queue.MAX_ATTEMPTS - 1):
            now += timedelta(hours=1)
            (again,) = job_queue.lease(s, agent.id, max_jobs=1, now=now)
            out = job_queue.complete(s, again.job_id, again.lease_id, agent.id, {}, retry, now=now)
        assert out["status"] == "failed"
        assert s.get(ScrapeJob, leased.job_id).status == "failed"


@pytest.mark.parametrize("status", ["blocked", "rejected", "failed"])
def test_terminal_outcomes_are_stored_with_their_reason(scratch_sessions, status):
    def process(job, upload):
        return {"status": status, "reason": f"because {status}"}

    with scratch_sessions() as s:
        agent, leased = _leased_job(s)
        out = job_queue.complete(s, leased.job_id, leased.lease_id, agent.id, {}, process, now=T0)
        job = s.get(ScrapeJob, leased.job_id)
    assert out == {"status": status, "reason": f"because {status}"}
    assert job.status == status
    assert job.reason == f"because {status}"


def test_a_processor_returning_an_unknown_status_is_an_error(scratch_sessions):
    with scratch_sessions() as s:
        agent, leased = _leased_job(s)
        with pytest.raises(ValueError):
            job_queue.complete(
                s, leased.job_id, leased.lease_id, agent.id, {}, lambda j, u: {"status": "ok"}, now=T0,
            )
        assert s.get(ScrapeJob, leased.job_id).status == "leased"


def test_a_done_job_can_be_queued_again(scratch_sessions):
    """The active-url uniqueness covers only queued/leased jobs: next cycle re-queues."""
    with scratch_sessions() as s:
        agent, leased = _leased_job(s)
        job_queue.complete(s, leased.job_id, leased.lease_id, agent.id, {}, _done, now=T0)
        job = s.get(ScrapeJob, leased.job_id)
        assert job_queue.enqueue(s, store_id=job.store_id, job_type="category_page", url=job.url)
