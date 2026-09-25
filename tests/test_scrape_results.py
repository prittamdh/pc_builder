"""Processing agent uploads (plan 02-02, AGENT-06/07/08/09).

Runs on the throwaway schema from conftest. A Shopify store keeps the fixtures small:
its listing and product pages are plain JSON the real GenericParser reads unchanged.
"""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from db.models.price_history import PriceHistory
from db.models.product import Product
from db.models.scrape_job import ScrapeJob
from db.models.scrape_target import ScrapeTarget
from db.models.store import Store
from pipeline import agent_tokens, job_queue, scrape_planning, scrape_results

T0 = datetime(2026, 10, 1, 12, 0, 0)
JSON_CT = "application/json; charset=utf-8"


def shopify_listing(handles, price="1000.00"):
    return json.dumps({"products": [
        {"title": f"Part {h}", "handle": h, "variants": [{"price": price, "available": True}], "images": []}
        for h in handles
    ]})


def shopify_product(handle, price="1500.00", available=True):
    return json.dumps({"product": {
        "title": f"Part {handle}", "handle": handle, "vendor": "AMD",
        "variants": [{"price": price, "compare_at_price": None, "available": available, "sku": handle.upper()}], "images": [],
    }})


@pytest.fixture
def env(scratch_sessions):
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
        schedule_config={"category": "CPU", "max_pages": 3}, next_scrape_at=T0,
    )
    s.add(target)
    s.commit()
    agent, _ = agent_tokens.create_agent(s, "laptop")
    yield s, store, target, agent
    s.close()


def upload(body, final_url="https://elitehubs.com/collections/cpu/products.json?limit=100",
           http_status=200, content_type=JSON_CT, error=None):
    return {"final_url": final_url, "http_status": http_status, "content_type": content_type,
            "body": body, "error": error}


def run(s, agent, up, now=T0):
    """Lease the one due job and upload `up` for it. Returns (job_id, outcome)."""
    (leased,) = job_queue.lease(s, agent.id, max_jobs=1, now=now)
    out = job_queue.complete(s, leased.job_id, leased.lease_id, agent.id, up, scrape_results.process_upload, now=now)
    return leased.job_id, out


def queue_page_one(s, target, now=T0):
    return scrape_planning.enqueue_targets(s, [target], now=now)


def price_rows(s):
    return s.execute(select(PriceHistory).order_by(PriceHistory.id)).scalars().all()


# --- listings ------------------------------------------------------------------------


def test_page_one_saves_prices_with_agent_and_job_and_queues_page_two(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    job_id, out = run(s, agent, upload(shopify_listing(["a", "b"])))

    assert out["status"] == "done"
    assert out["saved"] == 2
    rows = price_rows(s)
    assert len(rows) == 2
    assert {r.agent_id for r in rows} == {agent.id}
    assert {r.job_id for r in rows} == {job_id}
    products = s.execute(select(Product).order_by(Product.pid)).scalars().all()
    assert [p.pid for p in products] == ["a", "b"]
    assert products[0].category == "CPU"

    nxt = s.execute(select(ScrapeJob).where(ScrapeJob.status == "queued")).scalar_one()
    assert nxt.page == 2
    assert nxt.parent_job_id == job_id
    assert nxt.target_id == target.id
    assert nxt.url == "https://elitehubs.com/collections/cpu/products.json?limit=100&page=2"
    s.refresh(target)
    assert target.last_scraped_at == T0


def test_a_page_with_no_new_products_ends_the_listing(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    run(s, agent, upload(shopify_listing(["a", "b"])))
    _, out = run(s, agent, upload(shopify_listing(["b", "a"]),
                                  final_url="https://elitehubs.com/collections/cpu/products.json?limit=100&page=2"))
    assert out["status"] == "done"
    assert out["saved"] == 0
    assert out["next_job_id"] is None
    assert s.execute(select(func.count()).select_from(ScrapeJob).where(ScrapeJob.status == "queued")).scalar_one() == 0
    assert len(price_rows(s)) == 2


def test_new_ids_are_judged_against_every_earlier_page(env):
    s, store, target, agent = env
    target.schedule_config = {"category": "CPU", "max_pages": 5}
    s.commit()
    queue_page_one(s, target)
    run(s, agent, upload(shopify_listing(["a"])))
    run(s, agent, upload(shopify_listing(["b"])))
    # page 3 repeats page 1 only: nothing new, so no page 4
    _, out = run(s, agent, upload(shopify_listing(["a"])))
    assert out["next_job_id"] is None


def test_the_listing_stops_at_max_pages(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    for page, handle in enumerate(["a", "b", "c"], 1):
        _, out = run(s, agent, upload(shopify_listing([handle])))
    assert page == 3
    assert out["next_job_id"] is None
    assert len(price_rows(s)) == 3


def test_page_one_with_no_products_fails(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    _, out = run(s, agent, upload(shopify_listing([])))
    assert out["status"] == "failed"
    assert "0 products" in out["reason"]
    assert price_rows(s) == []


def test_a_later_empty_page_just_ends_the_listing(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    run(s, agent, upload(shopify_listing(["a"])))
    _, out = run(s, agent, upload(shopify_listing([])))
    assert out["status"] == "done"
    assert out["next_job_id"] is None


@pytest.mark.parametrize("status", [200, 403])
def test_a_challenge_page_is_blocked_and_saves_nothing(env, status):
    s, store, target, agent = env
    queue_page_one(s, target)
    body = "<html><title>Just a moment...</title><script>window._cf_chl_opt={cType: 'managed'}</script></html>"
    _, out = run(s, agent, upload(body, http_status=status, content_type="text/html"))
    assert out["status"] == "blocked"
    assert "challenge" in out["reason"]
    assert price_rows(s) == []


def test_a_redirect_to_a_login_page_is_blocked(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    _, out = run(s, agent, upload("<html>Sign in</html>", final_url="https://elitehubs.com/account/login",
                                  content_type="text/html"))
    assert out["status"] == "blocked"
    assert "login" in out["reason"]


@pytest.mark.parametrize("final_url", [
    "https://evil.example/collections/cpu/products.json",
    "https://elitehubs.com.evil.example/x",
    "not a url",
])
def test_an_upload_from_another_host_is_rejected(env, final_url):
    s, store, target, agent = env
    queue_page_one(s, target)
    _, out = run(s, agent, upload(shopify_listing(["a"]), final_url=final_url))
    assert out["status"] == "rejected"
    assert "host" in out["reason"]
    assert price_rows(s) == []


def test_a_body_over_5_mb_is_rejected(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    big = shopify_listing(["a"]) + " " * (5 * 1024 * 1024)
    _, out = run(s, agent, upload(big))
    assert out["status"] == "rejected"
    assert "5 MB" in out["reason"]
    assert price_rows(s) == []


def test_the_wrong_content_type_is_rejected(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    _, out = run(s, agent, upload("<html>maintenance</html>", content_type="text/html; charset=utf-8"))
    assert out["status"] == "rejected"
    assert "content type" in out["reason"]


@pytest.mark.parametrize("kwargs", [
    {"http_status": None, "body": None, "error": "timeout"},
    {"http_status": 429},
    {"http_status": 503},
])
def test_failed_fetches_are_retried(env, kwargs):
    s, store, target, agent = env
    queue_page_one(s, target)
    up = upload(shopify_listing(["a"]))
    up.update(kwargs)
    _, out = run(s, agent, up)
    assert out["status"] == "requeued"
    assert price_rows(s) == []


def test_a_404_on_page_one_fails_but_on_a_later_page_ends_the_listing(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    run(s, agent, upload(shopify_listing(["a"])))
    _, out = run(s, agent, upload("not found", http_status=404, content_type="text/html"))
    assert out["status"] == "done"
    assert out["next_job_id"] is None

    target.next_scrape_at = T0
    s.commit()
    queue_page_one(s, target, now=T0 + timedelta(hours=1))
    _, out = run(s, agent, upload("not found", http_status=404, content_type="text/html"), now=T0 + timedelta(hours=1))
    assert out["status"] == "failed"
    assert "404" in out["reason"]


def test_unusable_prices_are_dropped_and_counted(env):
    s, store, target, agent = env
    queue_page_one(s, target)
    body = json.dumps({"products": [
        {"title": "Zero", "handle": "zero", "variants": [{"price": "0.00", "available": True}], "images": []},
        {"title": "Huge", "handle": "huge", "variants": [{"price": "99999999.00", "available": True}], "images": []},
        {"title": "Fine", "handle": "fine", "variants": [{"price": "4999.00", "available": True}], "images": []},
    ]})
    _, out = run(s, agent, upload(body))
    assert out["status"] == "done"
    assert out["saved"] == 1
    assert out["dropped_prices"] == 2
    assert [r.price for r in price_rows(s)] == [4999]


def test_a_parser_crash_is_rejected_not_retried(env, monkeypatch):
    s, store, target, agent = env
    queue_page_one(s, target)

    def boom(self, html):
        raise ValueError("markup changed")

    monkeypatch.setattr("scrapers.generic_parser.GenericParser.parse_search", boom)
    _, out = run(s, agent, upload(shopify_listing(["a"])))
    assert out["status"] == "rejected"
    assert "markup changed" in out["reason"]


# --- product pages -------------------------------------------------------------------


def _product(s, store, pid="ryzen", price=1000):
    p = Product(sid=store.id, pid=pid, name=f"Part {pid}", product_url=f"https://elitehubs.com/products/{pid}",
                current_price=price, in_stock=True)
    s.add(p)
    s.commit()
    return p


def _queue_product(s, product, now=T0):
    return scrape_planning.enqueue_products(s, [product], now=now)


def test_a_product_page_updates_the_listing_and_records_agent_and_job(env):
    s, store, target, agent = env
    product = _product(s, store)
    _queue_product(s, product)
    job_id, out = run(s, agent, upload(shopify_product("ryzen", price="1500.00"),
                                       final_url="https://elitehubs.com/products/ryzen.json"))
    assert out["status"] == "done"
    s.refresh(product)
    assert float(product.current_price) == 1500.0
    (row,) = price_rows(s)
    assert (row.agent_id, row.job_id, float(row.price)) == (agent.id, job_id, 1500.0)


def test_a_product_page_404_marks_it_out_of_stock(env):
    s, store, target, agent = env
    product = _product(s, store)
    _queue_product(s, product)
    _, out = run(s, agent, upload("gone", http_status=404, content_type="text/html",
                                  final_url="https://elitehubs.com/products/ryzen.json"))
    assert out["status"] == "done"
    assert "out of stock" in out["reason"]
    s.refresh(product)
    assert product.in_stock is False
    assert price_rows(s) == []


def test_a_challenge_served_with_404_does_not_delist(env):
    s, store, target, agent = env
    product = _product(s, store)
    _queue_product(s, product)
    _, out = run(s, agent, upload("<title>Just a moment...</title>", http_status=404, content_type="text/html",
                                  final_url="https://elitehubs.com/products/ryzen.json"))
    assert out["status"] == "blocked"
    s.refresh(product)
    assert product.in_stock is True


def test_an_unparseable_product_page_is_rejected(env):
    s, store, target, agent = env
    product = _product(s, store)
    _queue_product(s, product)
    _, out = run(s, agent, upload("{}", final_url="https://elitehubs.com/products/ryzen.json"))
    assert out["status"] == "rejected"
    s.refresh(product)
    assert float(product.current_price) == 1000.0


# --- planning ------------------------------------------------------------------------


def test_due_targets_of_active_stores_get_a_page_one_job(env):
    s, store, target, agent = env
    off = Store(name="pcstudio", display_name="PCStudio", domain="pcstudio.in", base_url="https://www.pcstudio.in",
                search_endpoint="/", active=False)
    s.add(off)
    s.flush()
    s.add_all([
        ScrapeTarget(store_id=off.id, target_type=1, target_value="cpu", schedule_type=1, next_scrape_at=T0),
        ScrapeTarget(store_id=store.id, target_type=1, target_value="collections/gpu", schedule_type=1,
                     next_scrape_at=T0 + timedelta(hours=2)),  # not due
        ScrapeTarget(store_id=store.id, target_type=1, target_value="collections/ram", schedule_type=1,
                     next_scrape_at=T0, enabled=False),
    ])
    s.commit()

    assert scrape_planning.enqueue_due_targets(s, now=T0) == 1
    job = s.execute(select(ScrapeJob)).scalar_one()
    assert (job.target_id, job.page, job.job_type) == (target.id, 1, "category_page")
    s.refresh(target)
    assert target.next_scrape_at == T0 + timedelta(days=1)
    assert scrape_planning.enqueue_due_targets(s, now=T0) == 0


def test_unseen_products_get_product_page_jobs(env):
    s, store, target, agent = env
    stale = _product(s, store, pid="stale")
    fresh = _product(s, store, pid="fresh")
    s.add(PriceHistory(product_id=fresh.id, price=1000, scraped_at=T0 - timedelta(hours=1)))
    s.add(PriceHistory(product_id=stale.id, price=1000, scraped_at=T0 - timedelta(hours=9)))
    s.commit()
    found = scrape_planning.find_unseen_products(s, store.id, hours=3, now=T0)
    assert [p.pid for p in found] == ["stale"]
    assert scrape_planning.enqueue_products(s, found, now=T0) == 1
    job = s.execute(select(ScrapeJob)).scalar_one()
    assert (job.job_type, job.product_id, job.url) == (
        "product_page", stale.id, "https://elitehubs.com/products/stale.json",
    )
