"""The agent endpoints and /health/pipeline (plan 02-04, AGENT-04/06/12).

The app runs against the throwaway schema from conftest (get_db is overridden), so
nothing here touches the live catalog.
"""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.deps import get_db
from api.rate_limit import limiter
from db.models.pipeline_run import PipelineRun
from db.models.price_history import PriceHistory
from db.models.product import Product
from db.models.scrape_agent import ScrapeAgent
from db.models.scrape_job import ScrapeJob
from db.models.scrape_target import ScrapeTarget
from db.models.store import Store
from pipeline import agent_tokens, health, job_queue, scrape_planning

JSON_CT = "application/json; charset=utf-8"


def shopify_listing(handles, price="1000.00"):
    return json.dumps({"products": [
        {"title": f"Part {h}", "handle": h, "variants": [{"price": price, "available": True}], "images": []}
        for h in handles
    ]})


@pytest.fixture
def api(scratch_sessions):
    from api.main import app

    def _db():
        s = scratch_sessions()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    limiter.reset()
    s = scratch_sessions()
    store = Store(
        name="elitehubs", display_name="EliteHubs", domain="elitehubs.com",
        base_url="https://elitehubs.com", search_endpoint="https://elitehubs.com/search?q={query}",
        search_config={"platform": "shopify"}, product_config={"platform": "shopify"},
        active=True, min_fetch_interval_s=0,
    )
    s.add(store)
    s.flush()
    target = ScrapeTarget(
        store_id=store.id, target_type=1, target_value="collections/cpu", schedule_type=1,
        schedule_config={"category": "CPU", "max_pages": 2}, next_scrape_at=datetime(2026, 1, 1),
    )
    s.add(target)
    s.commit()
    agent, token = agent_tokens.create_agent(s, "laptop")
    try:
        yield TestClient(app), s, store, target, agent, token
    finally:
        s.close()
        app.dependency_overrides.pop(get_db, None)
        limiter.reset()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def lease_one(client, token):
    r = client.post("/api/agent/lease", json={"max_jobs": 1}, headers=auth(token))
    assert r.status_code == 200, r.text
    (job,) = r.json()["jobs"]
    return job


def result_body(job, page, **over):
    data = {
        "job_id": job["job_id"], "lease_id": job["lease_id"],
        "final_url": job["url"], "http_status": 200, "content_type": JSON_CT, "body": page, "error": None,
    }
    data.update(over)
    return data


# --- auth ----------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/agent/lease", "/api/agent/result", "/api/agent/heartbeat"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic abc"}])
def test_every_agent_endpoint_needs_a_valid_token(api, path, headers):
    client = api[0]
    r = client.post(path, json={}, headers=headers)
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_a_revoked_token_is_refused_on_its_next_call(api):
    client, s, store, target, agent, token = api
    assert client.post("/api/agent/heartbeat", json={}, headers=auth(token)).status_code == 200
    agent_tokens.revoke_agent(s, "laptop")
    assert client.post("/api/agent/heartbeat", json={}, headers=auth(token)).status_code == 401


def test_agent_endpoints_are_not_in_the_openapi_schema(api):
    client = api[0]
    paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith("/api/agent") or p.startswith("/health/pipeline")]


def test_the_rate_limit_is_per_token(api, monkeypatch):
    client, s, store, target, agent, token = api
    from configs import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_AGENT", "2/minute")
    _other, other_token = agent_tokens.create_agent(s, "desktop")
    for _ in range(2):
        assert client.post("/api/agent/heartbeat", json={}, headers=auth(token)).status_code == 200
    assert client.post("/api/agent/heartbeat", json={}, headers=auth(token)).status_code == 429
    assert client.post("/api/agent/heartbeat", json={}, headers=auth(other_token)).status_code == 200


# --- lease / result / heartbeat ------------------------------------------------------


def test_lease_returns_the_protocol_shape(api):
    client, s, store, target, agent, token = api
    scrape_planning.enqueue_targets(s, [target])
    job = lease_one(client, token)
    assert set(job) == {"job_id", "lease_id", "url", "headers", "store_host", "not_before"}
    assert job["url"] == "https://elitehubs.com/collections/cpu/products.json?limit=100"
    assert job["store_host"] == "elitehubs.com"
    datetime.fromisoformat(job["not_before"])  # ISO 8601
    assert "+" not in job["not_before"] and not job["not_before"].endswith("Z")


def test_an_empty_queue_leases_nothing(api):
    client, s, store, target, agent, token = api
    r = client.post("/api/agent/lease", json={"max_jobs": 5}, headers=auth(token))
    assert r.json() == {"jobs": []}


@pytest.mark.parametrize("max_jobs", [0, 51, "x"])
def test_max_jobs_out_of_range_is_a_400(api, max_jobs):
    client, s, store, target, agent, token = api
    r = client.post("/api/agent/lease", json={"max_jobs": max_jobs}, headers=auth(token))
    assert r.status_code == 400


def test_a_result_saves_once_and_replays(api):
    client, s, store, target, agent, token = api
    scrape_planning.enqueue_targets(s, [target])
    job = lease_one(client, token)
    body = result_body(job, shopify_listing(["a", "b"]))
    first = client.post("/api/agent/result", json=body, headers=auth(token))
    second = client.post("/api/agent/result", json=body, headers=auth(token))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"job_id": job["job_id"], "status": "done", "reason": None}
    rows = s.execute(select(PriceHistory)).scalars().all()
    assert len(rows) == 2
    assert {r.agent_id for r in rows} == {agent.id}


def test_a_result_for_a_stale_lease_is_409(api):
    client, s, store, target, agent, token = api
    scrape_planning.enqueue_targets(s, [target])
    job = lease_one(client, token)
    r = client.post("/api/agent/result", json=result_body(job, "{}", lease_id="wrong"), headers=auth(token))
    assert r.status_code == 409
    _other, other_token = agent_tokens.create_agent(s, "desktop")
    r = client.post("/api/agent/result", json=result_body(job, "{}"), headers=auth(other_token))
    assert r.status_code == 409
    assert s.execute(select(PriceHistory)).scalars().all() == []


@pytest.mark.parametrize("over, status, reason_has", [
    ({"final_url": "https://evil.example/x"}, "rejected", "host"),
    ({"body": "<title>Just a moment...</title>", "content_type": "text/html", "http_status": 403}, "blocked", "challenge"),
    ({"body": " " * (6 * 1024 * 1024)}, "rejected", "5 MB"),
    ({"body": shopify_listing([])}, "failed", "0 products"),
])
def test_doctored_uploads_are_stored_with_a_reason_and_save_nothing(api, over, status, reason_has):
    """Roadmap Phase 2 success criterion 4."""
    client, s, store, target, agent, token = api
    scrape_planning.enqueue_targets(s, [target])
    job = lease_one(client, token)
    r = client.post("/api/agent/result", json=result_body(job, shopify_listing(["a"]), **over), headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == status
    assert reason_has in r.json()["reason"]
    s.expire_all()
    stored = s.get(ScrapeJob, job["job_id"])
    assert stored.status == status
    assert reason_has in stored.reason
    assert s.execute(select(PriceHistory)).scalars().all() == []


def test_a_request_over_the_size_cap_is_413(api):
    client, s, store, target, agent, token = api
    scrape_planning.enqueue_targets(s, [target])
    job = lease_one(client, token)
    huge = json.dumps(result_body(job, "x" * (9 * 1024 * 1024)))
    r = client.post("/api/agent/result", content=huge, headers={**auth(token), "Content-Type": "application/json"})
    assert r.status_code == 413


def test_a_malformed_result_is_a_400(api):
    client, s, store, target, agent, token = api
    r = client.post("/api/agent/result", content=b"{not json", headers={**auth(token), "Content-Type": "application/json"})
    assert r.status_code == 400
    r = client.post("/api/agent/result", json={"job_id": "x"}, headers=auth(token))
    assert r.status_code == 400


def test_heartbeat_records_last_seen(api):
    client, s, store, target, agent, token = api
    r = client.post("/api/agent/heartbeat", json={"extension_version": "0.1.0"}, headers=auth(token))
    assert r.json() == {"ok": True}
    s.expire_all()
    assert s.get(ScrapeAgent, agent.id).last_seen_at is not None


# --- /health/pipeline ----------------------------------------------------------------


def _fresh_price(s, store, when):
    p = Product(sid=store.id, pid="x", name="X", product_url="https://elitehubs.com/products/x")
    s.add(p)
    s.flush()
    s.add(PriceHistory(product_id=p.id, price=100, scraped_at=when))
    s.commit()


def test_health_is_503_when_no_agent_has_checked_in(api):
    client, s, store, target, agent, token = api
    _fresh_price(s, store, job_queue.utcnow())
    r = client.get("/health/pipeline")
    assert r.status_code == 503
    assert any("agent" in p for p in r.json()["problems"])


def test_health_is_200_with_a_recent_agent_and_price(api):
    client, s, store, target, agent, token = api
    _fresh_price(s, store, job_queue.utcnow())
    client.post("/api/agent/heartbeat", json={}, headers=auth(token))
    r = client.get("/health/pipeline")
    assert r.status_code == 200, r.json()
    assert r.json()["problems"] == []
    assert "failed" in r.json()["jobs"]


def test_health_is_503_when_no_price_was_saved_for_a_day(api):
    client, s, store, target, agent, token = api
    _fresh_price(s, store, job_queue.utcnow() - timedelta(hours=25))
    client.post("/api/agent/heartbeat", json={}, headers=auth(token))
    r = client.get("/health/pipeline")
    assert r.status_code == 503
    assert any("price" in p for p in r.json()["problems"])


def test_health_is_503_when_a_scheduled_task_failed_or_is_overdue(api, monkeypatch):
    client, s, store, target, agent, token = api
    _fresh_price(s, store, job_queue.utcnow())
    client.post("/api/agent/heartbeat", json={}, headers=auth(token))
    monkeypatch.setattr(health, "SCHEDULED_TASKS", {"enqueue": timedelta(minutes=5), "reap": timedelta(minutes=5)})
    now = job_queue.utcnow()
    s.add_all([
        PipelineRun(task="enqueue", started_at=now - timedelta(minutes=1), status="failed", error="boom"),
        PipelineRun(task="reap", started_at=now - timedelta(minutes=11), finished_at=now, status="ok"),
    ])
    s.commit()
    problems = client.get("/health/pipeline").json()["problems"]
    assert any("enqueue" in p and "failed" in p for p in problems)
    assert any("reap" in p and "overdue" in p for p in problems)


def test_health_watches_the_nightly_backup_once_it_has_run(api):
    """03-03: the backup job records itself in pipeline_runs; a failed or late backup
    turns /health/pipeline red, the same way a failed worker task does."""
    client, s, store, target, agent, token = api
    _fresh_price(s, store, job_queue.utcnow())
    client.post("/api/agent/heartbeat", json={}, headers=auth(token))
    assert health.SCHEDULED_TASKS["db_backup"] == timedelta(days=1)
    s.add(PipelineRun(task="db_backup", started_at=job_queue.utcnow() - timedelta(days=3), status="ok"))
    s.commit()
    problems = client.get("/health/pipeline").json()["problems"]
    assert any("db_backup" in p and "overdue" in p for p in problems)
