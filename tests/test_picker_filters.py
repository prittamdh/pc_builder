"""Builder picker: brand and size chips, price range, sort, photos (2026-09-27).

Every category's picker list was long enough to scroll through blind, so the picker
now narrows the way people actually shop: brand, the size that matters for the part,
a price range. Reads the live database through the API, read-only.
"""
import pytest

from matching.size_from_title import ram_gb_from_title, screen_inches_from_title, size_label


@pytest.mark.parametrize("title, gb", [
    ("Corsair Vengeance 32GB (2x16GB) DDR5 6000MHz", 32),
    ("G.Skill Trident Z5 2x16GB DDR5", 32),
    ("Kingston Fury Beast 16GB DDR4 3200MHz", 16),
    ("Corsair Vengeance DDR5 RAM", None),
])
def test_ram_capacity(title, gb):
    assert ram_gb_from_title(title) == gb


@pytest.mark.parametrize("title, inches", [
    ('LG UltraGear 27GS75Q 27" QHD 180Hz', 27.0),
    ("Samsung Odyssey G5 32 inch Curved", 32.0),
    ("MSI MAG 274QRF 27-inch", 27.0),
    ("Acer Nitro VG240Y 23.8 inch", 23.8),
    ("Dell Monitor 1440p 165Hz", None),
])
def test_screen_size(title, inches):
    assert screen_inches_from_title(title) == inches


def test_size_labels():
    assert size_label("Storage", "Samsung 990 Pro 2TB") == "2TB"
    assert size_label("Power Supply", "RM850x 850W") == "850W"
    assert size_label("CPU", "Ryzen 5 7600") is None


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def pick(client, **body):
    body = {"slot": "gpu", "compatible_only": False, **body}
    r = client.post("/api/v1/builder/candidates", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_facets_list_brands_and_sizes(client):
    data = pick(client, q="9060")
    brands = {f["value"] for f in data["facets"]["brand"]}
    sizes = {f["value"] for f in data["facets"]["size"]}
    assert {"8GB", "16GB"} <= sizes
    assert len(brands) >= 3
    assert all(f["count"] > 0 for f in data["facets"]["brand"] + data["facets"]["size"])


def test_size_filter_keeps_only_that_size(client):
    data = pick(client, q="9060", size="16GB")
    assert data["items"]
    for m in data["items"]:
        assert all(size_label("GPU", o["name"]) == "16GB" for o in m["offers"]), m["name"]


def test_brand_filter(client):
    data = pick(client, q="9060", brand="Sapphire")
    assert data["items"]
    assert all(m["brand"] == "Sapphire" for m in data["items"])


def test_a_facet_does_not_constrain_itself(client):
    # With 16GB chosen, 8GB must still be offered, or switching needs a clear first.
    data = pick(client, q="9060", size="16GB")
    assert "8GB" in {f["value"] for f in data["facets"]["size"]}


def test_price_range(client):
    data = pick(client, q="9060", min_price=50000, max_price=60000)
    assert data["items"]
    assert all(50000 <= m["best_price"] <= 60000 for m in data["items"])


def test_sorts(client):
    desc = [m["best_price"] for m in pick(client, q="9060", sort="price_desc")["items"]]
    assert desc == sorted(desc, reverse=True)
    stores = [m["offer_count"] for m in pick(client, q="9060", sort="stores")["items"]]
    assert stores == sorted(stores, reverse=True)
    value = pick(client, q="9060", sort="value")["items"]
    premiums = [m["premium_pct"] for m in value]
    assert premiums == sorted(premiums)
    assert premiums[0] == 0


def test_unknown_sort_is_rejected(client):
    r = client.post("/api/v1/builder/candidates",
                    json={"slot": "gpu", "sort": "discount", "compatible_only": False})
    assert r.status_code == 422


def test_models_carry_a_photo_field(client):
    items = pick(client, q="9060")["items"]
    assert all("image_url" in m for m in items)
    assert any(m["image_url"] for m in items)


def test_search_ignores_spacing(client):
    # "9060xt" must find titles written "RX 9060 XT", as the catalog search does.
    assert pick(client, q="9060xt")["items"]
