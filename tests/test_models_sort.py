"""Every sort the catalog's dropdown offers must work on /products/models.

The dropdown offered "Recently Updated" while /models accepted only the price and name
sorts, so picking it replaced the catalog with "Failed to load catalog products: 422"
(found on the live site 2026-09-26). Reads the live database, read-only.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def dropdown_sorts():
    html = (ROOT / "src" / "static" / "index.html").read_text(encoding="utf-8")
    select = re.search(r'<select id="sort-select">(.*?)</select>', html, re.S).group(1)
    return re.findall(r'<option value="([^"]+)"', select)


def test_dropdown_offers_sorts():
    assert "recent" in dropdown_sorts()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


@pytest.mark.parametrize("sort", dropdown_sorts())
def test_models_accepts_every_dropdown_sort(client, sort):
    r = client.get("/api/v1/products/models", params={"sort": sort, "size": 5})
    assert r.status_code == 200, r.text
    assert r.json()["items"], "catalog is empty"


def test_models_rejects_unknown_sort(client):
    assert client.get("/api/v1/products/models", params={"sort": "discount"}).status_code == 422
