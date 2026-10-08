"""The server never fetches retailer pages in production (plan 02-02, AGENT-08).

Store pages come through agent jobs. The server-side HttpClient still works in
development, for tests and local debugging, but in production it refuses every store
host before sending anything.
"""
import re
from pathlib import Path

import pytest

from scrapers import http_client
from scrapers.http_client import HttpClient, ServerFetchRefused
from scrapers.store_hosts import STORE_DOMAINS, is_store_host

ROOT = Path(__file__).resolve().parent.parent


class _FakeSession:
    def __init__(self):
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)

        class R:
            status_code = 200

            def raise_for_status(self):
                pass

        return R()

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    c = HttpClient()
    c.session = _FakeSession()
    return c


@pytest.mark.parametrize("url", [
    "https://mdcomputers.in/catalog/processor",
    "https://www.vedantcomputers.com/x",
    "https://shop.clarioncomputers.in/products?category=cpu",
    "https://WWW.TPSTECH.IN/collections/gpu/products.json",
])
def test_production_refuses_store_hosts_before_sending(client, monkeypatch, url):
    monkeypatch.setattr(http_client, "_is_production", lambda: True)
    with pytest.raises(ServerFetchRefused):
        client.get(url)
    assert client.session.urls == []


def test_production_still_fetches_other_hosts(client, monkeypatch):
    monkeypatch.setattr(http_client, "_is_production", lambda: True)
    client.get("https://www.corsair.com/us/en/p/cases/cc-9011")  # a manufacturer page (Phase 4)
    assert client.session.urls == ["https://www.corsair.com/us/en/p/cases/cc-9011"]


def test_development_fetches_store_hosts(client, monkeypatch):
    monkeypatch.setattr(http_client, "_is_production", lambda: False)
    client.get("https://mdcomputers.in/catalog/processor")
    assert client.session.urls == ["https://mdcomputers.in/catalog/processor"]


def test_production_is_read_from_settings(monkeypatch):
    from configs import settings

    monkeypatch.setattr(settings, "ENV", "production")
    assert http_client._is_production() is True
    monkeypatch.setattr(settings, "ENV", "development")
    assert http_client._is_production() is False


def test_host_matching_is_by_domain_not_substring():
    assert is_store_host("www.primeabgb.com")
    assert not is_store_host("primeabgb.com.evil.example")
    assert not is_store_host("notmdcomputers.in")


def test_the_host_list_covers_every_store_in_the_database():
    """Read-only against the live DB: a new store must be added to STORE_DOMAINS (and to
    the extension's manifest) or its jobs could be fetched server-side in production."""
    from sqlalchemy import select

    from db.models.store import Store
    from db.session import SessionLocal

    with SessionLocal() as s:
        domains = {d.lower() for d in s.execute(select(Store.domain)).scalars() if d}
    if not domains:
        pytest.skip("no stores in the database")
    assert domains <= set(STORE_DOMAINS)


# Scripts that still fetch store pages with HttpClient, and why that's allowed for now.
# Every one of them is refused in production by the check above.
STILL_FETCHING = {
    "scripts/scrape_cabinet_clearance.py": "moves to product_page jobs in Phase 4 (04-01)",
    "scripts/scrape_cabinet_radiators.py": "moves to product_page jobs in Phase 4 (04-01)",
    "scripts/scrape_cooler_height.py": "moves to product_page jobs in Phase 4 (04-01)",
    "scripts/scrape_psu_efficiency.py": "moves to product_page jobs in Phase 4 (04-01)",
    "dags/scheduled_scraper_dag.py": "local Airflow only; the worker (02-03) replaces it",
    "src/main.py": "old local debug entry point (MDComputers search)",
}


def test_no_other_script_fetches_store_pages_directly():
    users = set()
    for folder in ("scripts", "dags", "src"):
        for path in (ROOT / folder).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith("src/scrapers/"):
                continue
            if re.search(r"\bHttpClient\b", path.read_text(encoding="utf-8", errors="replace")):
                users.add(rel)
    assert users <= set(STILL_FETCHING), sorted(users - set(STILL_FETCHING))
