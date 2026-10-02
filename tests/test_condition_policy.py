"""Only new, retail-boxed stock is listed (owner decision 2026-10-02).

Open box, repacked, refurbished and OEM/tray listings are hidden from the catalog,
the builder and price comparison. OEM CPUs are new chips without the retail box and
cooler; the owner chose to treat them as not-new too.
"""
import pytest

from matching.condition_policy import OEM, OPEN_BOX, REPACKED, detect_condition


@pytest.mark.parametrize("title, category", [
    ("AMD Ryzen 7 5700X OEM Tray Processor (3 Years Waranty)", "CPU"),
    ("AMD Ryzen 7 7800X3D Gaming Processor OEM Pack no stock cooler", "CPU"),
    ("AMD Ryzen Threadripper PRO 9975WX 4.0 GHz 32-Core sTR5 Processor Tray", "CPU"),
    ("Intel Core i5-12400F Tray Processor", "CPU"),
    ("Intel Core i7 14700 MPK Processor", "CPU"),
    ("Intel Core i5 12400F Multipack", "CPU"),
    ("Zotac RTX 3050 6GB OEM Graphics Card", "GPU"),
])
def test_oem_and_tray_are_not_new(title, category):
    assert detect_condition(title, category) == OEM


@pytest.mark.parametrize("title, category", [
    # Retail-boxed CPUs: WOF is AMD's "without fan" retail box, BOX/BX Intel's.
    ("AMD Ryzen 7 7800X3D Gaming Processor 100-100000910WOF", "CPU"),
    ("Intel Core I5-14400F Processor BX8071514400F", "CPU"),
    ("AMD Ryzen 5 8600G Desktop Processor 100-100001237BOX", "CPU"),
    # "tray" outside CPUs is a part of the product, not a sale condition.
    ("Lian Li O11 Dynamic EVO Cabinet with 2 HDD Tray", "Cabinet"),
    ("Ant Esports ICE-100 Mid Tower with SSD tray", "Cabinet"),
])
def test_retail_and_ordinary_titles_stay_new(title, category):
    assert detect_condition(title, category) is None


def test_open_box_oem_counts_as_open_box():
    # Opened stock is the stronger signal; it was flagged before OEM was.
    assert detect_condition("AMD Ryzen 7 7975WX Open Box OEM Processor", "CPU") == OPEN_BOX
    assert detect_condition("[RePacked] AMD Ryzen 5 7600", "CPU") == REPACKED


def test_category_is_optional():
    assert detect_condition("Ryzen 5 5600 OEM") == OEM
    assert detect_condition("Cabinet with drive tray") is None


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_lists_only_new_stock(client):
    """Reads the live database: nothing that is not new reaches the catalog, the
    grouped catalog or the builder."""
    flat = client.get("/api/v1/products", params={"q": "oem", "size": 50}).json()["items"]
    assert all(i["condition"] is None for i in flat)
    opened = client.get("/api/v1/products", params={"q": "open box", "size": 50}).json()["items"]
    assert opened == []
    models = client.get("/api/v1/products/models", params={"p_category": "CPU", "size": 60}).json()["items"]
    assert all(m["condition"] is None for m in models)
    picked = client.post("/api/v1/builder/candidates",
                         json={"slot": "cpu", "compatible_only": False}).json()["items"]
    assert all(o["condition"] is None for m in picked for o in m["offers"])
