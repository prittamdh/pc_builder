"""SEC-03: per-IP rate limits, a JSON 429, and a spoofing-safe key function.

All settings the limiter reads (RATE_LIMIT_*, TRUST_CF_CONNECTING_IP) are read
live off `configs.settings` on every request - see api/rate_limit.py's
docstring - so these tests monkeypatch the settings module directly and reset
the limiter's in-memory counters between cases with `limiter.reset()`, rather
than reloading modules or booting a subprocess.
"""
import pytest
from fastapi.testclient import TestClient

from api.deps import get_db
from api.main import app
from api.rate_limit import limiter, rate_limit_key
from configs import settings

HOSTS = frozenset({"pcstudio.in"})


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Every test in this file gets a clean counter and its own settings
    restored afterward (monkeypatch handles the settings restore)."""
    limiter.reset()
    yield
    limiter.reset()


class _FakeStream:
    """A same-shaped stand-in for httpx's streamed response - status/content
    only matter to test_image_proxy.py; here only the request COUNTS toward
    the limiter, so any quick, non-network response will do."""

    def __init__(self):
        self.status_code = 200
        self.headers = {"content-type": "text/html"}
        self.is_redirect = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def iter_bytes(self):
        return iter(())


class _FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def stream(self, method, url):
        return _FakeStream()


@pytest.fixture
def client(monkeypatch):
    # /api/v1/images needs a DB session (for store_hosts) and a store URL;
    # stub both, plus the outbound httpx client, so these tests only exercise
    # the limiter - never the network or the live DB.
    monkeypatch.setattr("api.routes.images.store_hosts", lambda db: HOSTS)
    monkeypatch.setattr("api.routes.images.httpx.Client", lambda *a, **k: _FakeClient())
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _get_health(client):
    return client.get("/health")


def _get_image(client):
    return client.get("/api/v1/images", params={"u": "https://pcstudio.in/x.jpg"})


def test_third_image_request_is_429_json(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", "2/minute")
    assert _get_image(client).status_code != 429
    assert _get_image(client).status_code != 429
    resp = _get_image(client)
    assert resp.status_code == 429
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["detail"]


def test_third_health_request_is_429_json_under_default_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_DEFAULT", "2/minute")
    assert _get_health(client).status_code != 429
    assert _get_health(client).status_code != 429
    resp = _get_health(client)
    assert resp.status_code == 429
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["detail"]


def test_429_carries_security_headers(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_DEFAULT", "1/minute")
    _get_health(client)
    resp = _get_health(client)
    assert resp.status_code == 429
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert "content-security-policy" in resp.headers


def test_edge_boundary_first_two_ok_third_429(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", "2/minute")
    codes = [_get_image(client).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_rate_limit_enabled_false_never_429s(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", "1/minute")
    monkeypatch.setattr(limiter, "enabled", False)
    codes = [_get_image(client).status_code for _ in range(10)]
    assert 429 not in codes


def test_retry_is_not_free_idempotency(client, monkeypatch):
    """A retry of the identical request still counts - no free re-try."""
    monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", "1/minute")
    assert _get_image(client).status_code == 200
    assert _get_image(client).status_code == 429
    assert _get_image(client).status_code == 429


def test_ordering_every_further_request_429_until_window_resets(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", "1/minute")
    monkeypatch.setattr(settings, "RATE_LIMIT_DEFAULT", "100/minute")
    assert _get_image(client).status_code == 200
    for _ in range(5):
        assert _get_image(client).status_code == 429


# --- SEC-03: CF-Connecting-IP is only trusted when explicitly told to. -------

def test_untrusted_header_is_ignored_shared_bucket(client, monkeypatch):
    """TRUST_CF_CONNECTING_IP is false (the default): varying the header does
    NOT reset the count, because the key is the real socket address, which the
    TestClient keeps constant across requests."""
    monkeypatch.setattr(settings, "TRUST_CF_CONNECTING_IP", False)
    monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", "1/minute")
    assert _get_image(client).status_code == 200
    resp = client.get(
        "/api/v1/images",
        params={"u": "https://pcstudio.in/x.jpg"},
        headers={"CF-Connecting-IP": "9.9.9.9"},
    )
    assert resp.status_code == 429


def test_trusted_header_gives_independent_counters_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "TRUST_CF_CONNECTING_IP", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", "1/minute")
    r1 = client.get("/api/v1/images", params={"u": "https://pcstudio.in/x.jpg"},
                     headers={"CF-Connecting-IP": "1.1.1.1"})
    assert r1.status_code == 200
    # 1.1.1.1 is now exhausted, but 2.2.2.2 has its own independent counter.
    r2 = client.get("/api/v1/images", params={"u": "https://pcstudio.in/x.jpg"},
                     headers={"CF-Connecting-IP": "2.2.2.2"})
    assert r2.status_code == 200
    r3 = client.get("/api/v1/images", params={"u": "https://pcstudio.in/x.jpg"},
                     headers={"CF-Connecting-IP": "1.1.1.1"})
    assert r3.status_code == 429


def test_trusted_but_missing_header_falls_back_to_socket_address(client, monkeypatch):
    """No shared empty-string bucket: with the header absent, the key must
    fall back to the real address, not "" for everyone."""
    monkeypatch.setattr(settings, "TRUST_CF_CONNECTING_IP", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", "1/minute")
    r1 = _get_image(client)
    assert r1.status_code == 200
    r2 = _get_image(client)
    assert r2.status_code == 429


class _FakeRequest:
    """A minimal stand-in for starlette.requests.Request - just enough for
    rate_limit_key(), which only reads .headers and passes the request
    through to get_remote_address (via .client.host)."""

    def __init__(self, headers, host="1.2.3.4"):
        self.headers = headers
        self.client = type("C", (), {"host": host})()


def test_rate_limit_key_strips_whitespace_around_the_header(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_CF_CONNECTING_IP", True)
    key = rate_limit_key(_FakeRequest({"CF-Connecting-IP": "  5.5.5.5  "}))
    assert key == "5.5.5.5"


def test_rate_limit_key_falls_back_when_header_is_blank(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_CF_CONNECTING_IP", True)
    key = rate_limit_key(_FakeRequest({"CF-Connecting-IP": "   "}, host="1.2.3.4"))
    assert key == "1.2.3.4"


def test_trusted_but_blank_header_falls_back_to_socket_address(client, monkeypatch):
    """Fix round 1: a present-but-blank/whitespace-only CF-Connecting-IP must
    not become the literal key "" (which every such client would then share) -
    it must fall back to the real socket address, same as a missing header."""
    monkeypatch.setattr(settings, "TRUST_CF_CONNECTING_IP", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", "1/minute")
    r1 = client.get("/api/v1/images", params={"u": "https://pcstudio.in/x.jpg"},
                     headers={"CF-Connecting-IP": "   "})
    assert r1.status_code == 200
    r2 = client.get("/api/v1/images", params={"u": "https://pcstudio.in/x.jpg"},
                     headers={"CF-Connecting-IP": "   "})
    assert r2.status_code == 429


# --- F1: the limiter must key by endpoint (route pattern), not exact URL, ---
# --- so parameterised paths (/products/{id}, /builds/{token}) share one ----
# --- counter across different path-parameter values. ------------------------

class _StubProductSession:
    """A get_db stand-in that never touches the live DB: db.get() always
    reports 'no row', so GET /api/v1/products/{id} takes the 404 branch for
    any id - the only thing under test is whether the request is counted."""

    def get(self, model, pk):
        return None


class _StubBuildSession:
    """A get_db stand-in for GET /api/v1/builder/builds/{token}: db.scalar()
    always reports 'no row', so any token takes the 404 branch."""

    def scalar(self, *a, **k):
        return None


@pytest.fixture
def stub_product_db():
    app.dependency_overrides[get_db] = lambda: _StubProductSession()
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def stub_build_db():
    app.dependency_overrides[get_db] = lambda: _StubBuildSession()
    yield
    app.dependency_overrides.pop(get_db, None)


def test_products_by_id_limit_is_shared_across_different_ids(monkeypatch, stub_product_db):
    """Reviewer-proven bug: slowapi's default key_style is per-exact-URL, so
    /api/v1/products/1, /products/2, /products/3 each get their own counter
    and a parameterised route is effectively unlimited. With key_style set to
    "endpoint" they share one counter keyed by route pattern."""
    monkeypatch.setattr(settings, "RATE_LIMIT_DEFAULT", "2/minute")
    with TestClient(app) as c:
        codes = [c.get(f"/api/v1/products/{i}").status_code for i in range(1, 4)]
    assert codes == [404, 404, 429]


def test_builds_by_token_limit_is_shared_across_different_tokens(monkeypatch, stub_build_db):
    monkeypatch.setattr(settings, "RATE_LIMIT_BUILDER", "2/minute")
    tokens = ["aaaa-unknown", "bbbb-unknown", "cccc-unknown"]
    with TestClient(app) as c:
        codes = [c.get(f"/api/v1/builder/builds/{t}").status_code for t in tokens]
    assert codes == [404, 404, 429]


def test_validate_route_limit_applies(monkeypatch):
    """/api/v1/builder/validate: an empty selection list short-circuits before
    any DB query (see BuilderService.validate_and_calculate_build), so this
    only exercises the limiter."""
    monkeypatch.setattr(settings, "RATE_LIMIT_BUILDER", "2/minute")
    with TestClient(app) as c:
        codes = [
            c.post("/api/v1/builder/validate", json={"selected_product_ids": []}).status_code
            for _ in range(3)
        ]
    assert codes == [200, 200, 429]


def test_candidates_route_limit_applies(monkeypatch):
    """/api/v1/builder/candidates: an unknown slot returns early without
    touching the DB, so this only exercises the limiter."""
    monkeypatch.setattr(settings, "RATE_LIMIT_BUILDER", "2/minute")
    with TestClient(app) as c:
        codes = [
            c.post("/api/v1/builder/candidates", json={"slot": "not-a-real-slot"}).status_code
            for _ in range(3)
        ]
    assert codes == [200, 200, 429]
