"""SEO-01: head tags on the home page, favicon, robots.txt and sitemap.xml."""
import re
import xml.etree.ElementTree as ET

from starlette.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_home_has_single_title_containing_pc_builder():
    html = client.get("/").text
    titles = re.findall(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    assert len(titles) == 1
    assert "PC Builder" in titles[0]


def test_home_has_meta_description():
    html = client.get("/").text
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html)
    assert m and m.group(1).strip()


def test_home_has_og_tags():
    html = client.get("/").text
    assert re.search(r'property=["\']og:title["\']', html)
    assert re.search(r'property=["\']og:description["\']', html)
    assert re.search(r'property=["\']og:type["\']', html)


def test_home_has_favicon_link_and_favicon_serves():
    html = client.get("/").text
    assert re.search(r'rel=["\']icon["\'][^>]+href=["\']/static/favicon\.svg["\']', html)
    resp = client.get("/static/favicon.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")


def test_home_has_canonical_link():
    html = client.get("/").text
    assert re.search(r'rel=["\']canonical["\']', html)


def test_robots_txt():
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "User-agent: *" in body
    assert "Disallow: /api/" in body
    assert re.search(r"Sitemap: https?://\S+", body)


def test_sitemap_xml_is_valid_and_absolute():
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "xml" in resp.headers["content-type"]
    root = ET.fromstring(resp.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.text for el in root.findall("s:url/s:loc", ns)]
    assert locs, "sitemap has no <loc> entries"
    for loc in locs:
        assert loc.startswith("http://") or loc.startswith("https://")
    paths = {re.sub(r"^https?://[^/]+", "", loc) for loc in locs}
    assert "/" in paths
    assert "/about" in paths
    assert "/privacy" in paths
