"""/health and /health/freshness for the uptime monitor (plan 03-02, OPS-04)."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api.deps import get_db
from db.models.price_history import PriceHistory
from db.models.product import Product
from db.models.store import Store
from pipeline.job_queue import utcnow


@pytest.fixture
def client_on(scratch_sessions):
    from api.main import app

    def _db():
        s = scratch_sessions()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    try:
        yield TestClient(app), scratch_sessions
    finally:
        app.dependency_overrides.pop(get_db, None)


def _price(sessions, when):
    with sessions() as s:
        store = Store(name="md", display_name="MD", domain="mdcomputers.in", search_endpoint="/")
        s.add(store)
        s.flush()
        p = Product(sid=store.id, pid="1", name="CPU", product_url="https://mdcomputers.in/p")
        s.add(p)
        s.flush()
        s.add(PriceHistory(product_id=p.id, price=100, scraped_at=when))
        s.commit()


def test_health_is_ok_when_the_database_answers(client_on):
    client, _ = client_on
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_is_503_when_the_database_is_down():
    from api.main import app

    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("connection refused")

        def close(self):
            pass

    app.dependency_overrides[get_db] = lambda: Broken()
    try:
        r = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 503
    assert r.json()["status"] == "fail"
    assert "connection refused" not in r.text  # no internals to the public


def test_freshness_is_ok_with_a_recent_price(client_on):
    client, sessions = client_on
    _price(sessions, utcnow() - timedelta(hours=2))
    r = client.get("/health/freshness")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize("age", [timedelta(hours=25), None])
def test_freshness_is_503_when_prices_are_stale_or_missing(client_on, age):
    client, sessions = client_on
    if age is not None:
        _price(sessions, utcnow() - age)
    r = client.get("/health/freshness")
    assert r.status_code == 503
    assert r.json()["status"] == "fail"


def test_health_endpoints_are_not_in_the_public_schema(client_on):
    client, _ = client_on
    paths = client.get("/openapi.json").json()["paths"]
    assert "/health/freshness" not in paths
