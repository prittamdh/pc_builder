"""Listings from inactive stores must not show anywhere on the site.

PCStudio (sid 2) was set inactive on 2026-09-25 when it went behind a Cloudflare bot
check; its last prices are from 2026-08-17 and would otherwise show as current.
Re-enabling a store must bring its listings back with no other change, so the filter
reads stores.active at query time rather than copying the flag anywhere.

The API tests read the live database (read-only) and need at least one inactive store
with listings; they skip, loudly, when there is none.
"""

import pytest
from sqlalchemy import select

from api.filters import from_active_store


def test_filter_reads_the_store_flag_at_query_time():
    sql = str(from_active_store().compile(compile_kwargs={"literal_binds": True})).lower()
    assert "stores.active" in sql
    assert "products.sid" in sql


@pytest.fixture(scope="module")
def inactive_listing():
    from db.session import SessionLocal
    from db.models.product import Product
    from db.models.store import Store

    with SessionLocal() as s:
        row = s.execute(
            select(Product.id, Product.sid, Product.canonical_id)
            .join(Store, Store.id == Product.sid)
            .where(Store.active.is_(False))
            .limit(1)
        ).first()
        active = s.execute(
            select(Product.id)
            .join(Store, Store.id == Product.sid)
            .where(Store.active.is_(True), Product.current_price > 0)
            .limit(1)
        ).first()
    if row is None or active is None:
        pytest.skip("needs one inactive store with listings and one active listing")
    return {"id": row.id, "sid": row.sid, "canonical_id": row.canonical_id, "active_id": active.id}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_catalog_hides_inactive_store(client, inactive_listing):
    r = client.get("/api/v1/products", params={"sid": inactive_listing["sid"], "include_unpriced": True})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_inactive_store_product_page_is_404(client, inactive_listing):
    for path in ("", "/history", "/price-series"):
        r = client.get(f"/api/v1/products/{inactive_listing['id']}{path}")
        assert r.status_code == 404, path


def test_active_store_product_still_served(client, inactive_listing):
    for path in ("", "/history", "/price-series"):
        r = client.get(f"/api/v1/products/{inactive_listing['active_id']}{path}")
        assert r.status_code == 200, path


def test_models_view_has_no_inactive_listing(client, inactive_listing):
    r = client.get("/api/v1/products/models", params={"sid": inactive_listing["sid"]})
    assert r.status_code == 200
    body = r.json()
    items = body.get("items", body if isinstance(body, list) else [])
    assert all(
        l.get("sid") != inactive_listing["sid"]
        for m in items
        for l in m.get("listings", [])
    )
