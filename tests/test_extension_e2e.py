"""The Chrome extension end to end (plan 02-05, AGENT-10).

Real Chromium with the unpacked extension, the real API (on the throwaway schema, in a
background thread), and a fixture store page: Playwright answers the extension's fetch
of elitehubs.com, so no real store is contacted. Clicking "Run now" on the options page
must lease the job, fetch the page, upload it, and save prices tagged with the agent.

Skipped when Playwright or its Chromium is missing, unless REQUIRE_E2E=1 (as for
test_frontend_e2e.py).
"""
import json
import os
import re
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "extension"


def _skip_or_fail(reason):
    if os.environ.get("REQUIRE_E2E") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(scratch_sessions):
    import uvicorn

    from api.deps import get_db
    from api.main import app
    from api.rate_limit import limiter

    def _db():
        s = scratch_sessions()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    limiter.reset()
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.should_exit = True
        thread.join(timeout=10)
        app.dependency_overrides.pop(get_db, None)


def test_the_extension_fetches_a_job_and_the_server_saves_it(server, scratch_sessions, tmp_path, monkeypatch):
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        _skip_or_fail("playwright not installed")

    from db.models.price_history import PriceHistory
    from db.models.scrape_job import ScrapeJob
    from db.models.scrape_target import ScrapeTarget
    from db.models.store import Store
    from pipeline import agent_tokens, scrape_planning

    with scratch_sessions() as s:
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
            schedule_config={"category": "CPU", "max_pages": 1}, next_scrape_at=datetime(2026, 1, 1),
        )
        s.add(target)
        s.commit()
        agent, token = agent_tokens.create_agent(s, "e2e")
        scrape_planning.enqueue_targets(s, [target])

    page_body = json.dumps({"products": [
        {"title": "Ryzen 5 7600", "handle": "ryzen-5-7600",
         "variants": [{"price": "17999.00", "available": True}], "images": []},
        {"title": "Ryzen 7 7700", "handle": "ryzen-7-7700",
         "variants": [{"price": "25999.00", "available": True}], "images": []},
    ]})
    store_requests = []

    # Lets Playwright see and answer requests made by the extension's service worker.
    monkeypatch.setenv("PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS", "1")
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                str(tmp_path / "profile"),
                channel="chromium",
                headless=True,
                args=[f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"],
            )
        except Exception as exc:  # chromium missing or can't start
            _skip_or_fail(f"chromium unavailable: {exc}")

        def store_page(route):
            store_requests.append({"url": route.request.url, "headers": route.request.headers})
            route.fulfill(status=200, body=page_body, headers={"content-type": "application/json; charset=utf-8"})

        context.route("https://elitehubs.com/**", store_page)
        try:
            sw = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
            ext_id = sw.url.split("/")[2]
            sw.evaluate(
                "cfg => chrome.storage.local.set(cfg)",
                {"serverUrl": server, "token": token, "enabled": True, "maxJobs": 5},
            )
            options = context.new_page()
            options.goto(f"chrome-extension://{ext_id}/options.html")
            options.click("#test")
            # Extension pages forbid eval, so wait with locators, not wait_for_function.
            expect(options.locator("#msg")).to_have_text(re.compile("^Connected"), timeout=15000)
            options.click("#run")
            expect(options.locator("#msg")).to_have_text("Batch finished.", timeout=30000)
            status_text = options.inner_text("#status")
        finally:
            context.close()

    assert [r["url"] for r in store_requests] == [
        "https://elitehubs.com/collections/cpu/products.json?limit=100"
    ]
    assert "cookie" not in {k.lower() for k in store_requests[0]["headers"]}
    assert '"done":1' in status_text

    with scratch_sessions() as s:
        job = s.execute(select(ScrapeJob)).scalar_one()
        assert job.status == "done", (job.status, job.reason)
        rows = s.execute(select(PriceHistory)).scalars().all()
        assert sorted(float(r.price) for r in rows) == [17999.0, 25999.0]
        assert {r.agent_id for r in rows} == {agent.id}
        assert {r.job_id for r in rows} == {job.id}
