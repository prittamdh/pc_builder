"""SEC-05: every response carries baseline security headers, no HSTS from the app."""
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_index_has_nosniff():
    resp = client.get("/")
    assert resp.headers.get("x-content-type-options") == "nosniff"


def test_index_has_referrer_policy():
    resp = client.get("/")
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_index_has_csp_with_frame_ancestors_and_fonts():
    resp = client.get("/")
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in csp
    assert "fonts.googleapis.com" in csp
    assert "fonts.gstatic.com" in csp


def test_index_has_no_hsts():
    resp = client.get("/")
    assert "strict-transport-security" not in {k.lower() for k in resp.headers.keys()}


def test_json_response_has_same_headers():
    resp = client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in resp.headers.get("content-security-policy", "")
