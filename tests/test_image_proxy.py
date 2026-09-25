"""The image route fetches server-side, so it must only ever fetch from store hosts."""
import types

import httpx
import pytest
from fastapi.testclient import TestClient

from api.deps import get_db
from api.main import app
from api.rate_limit import limiter
from api.routes.images import MAX_BYTES, _host, is_allowed

HOSTS = frozenset({"pcstudio.in", "mdcomputers.in"})


def test_store_image_allowed():
    assert is_allowed("https://www.pcstudio.in/wp-content/uploads/x.webp", HOSTS)
    assert is_allowed("https://mdcomputers.in/image/catalog/a.jpg", HOSTS)


def test_subdomain_of_store_allowed():
    assert is_allowed("https://cdn.mdcomputers.in/a.jpg", HOSTS)


def test_other_hosts_refused():
    assert not is_allowed("https://evil.example/a.jpg", HOSTS)
    assert not is_allowed("http://127.0.0.1:8000/admin", HOSTS)
    assert not is_allowed("http://169.254.169.254/latest/meta-data", HOSTS)


def test_lookalike_host_refused():
    assert not is_allowed("https://notpcstudio.in/a.jpg", HOSTS)
    assert not is_allowed("https://pcstudio.in.evil.example/a.jpg", HOSTS)


def test_non_http_schemes_refused():
    assert not is_allowed("file:///etc/passwd", HOSTS)
    assert not is_allowed("ftp://pcstudio.in/a.jpg", HOSTS)


def test_host_normalises_www():
    assert _host("https://WWW.PCStudio.in/x") == "pcstudio.in"


def test_store_cdns_allowed_exactly():
    assert is_allowed("https://cdn.shopify.com/s/files/1/x.jpg", HOSTS)
    assert is_allowed("https://tlggaming.b-cdn.net/a.webp", HOSTS)
    assert not is_allowed("https://someoneelse.b-cdn.net/a.webp", HOSTS)


# --- SEC-04: the proxy never relays a non-image, and streams (never fully
# buffers) an oversized body before serving the placeholder instead. ---------

class _FakeStream:
    """Stands in for the object `httpx.Client.stream(...)` yields. Tracks how
    many bytes were actually pulled through iter_bytes(), so a test can prove
    the route stopped reading at the cap instead of buffering everything."""

    def __init__(self, status_code=200, content_type="image/png", chunks=(),
                 is_redirect=False, next_url=None):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.is_redirect = is_redirect
        self.next_request = types.SimpleNamespace(url=next_url) if next_url else None
        self._chunks = list(chunks)
        self.bytes_read = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def iter_bytes(self):
        for chunk in self._chunks:
            self.bytes_read += len(chunk)
            yield chunk


class _FakeClient:
    """Stands in for `httpx.Client(...)`. `stream()` returns the next
    pre-built `_FakeStream` in order, one per redirect hop plus the final
    fetch - exactly what the real per-hop redirect loop calls."""

    def __init__(self, streams):
        self._streams = list(streams)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def stream(self, method, url):
        return self._streams.pop(0)


@pytest.fixture
def image_env(monkeypatch):
    """Product_image needs a DB session (for store_hosts) and an httpx client;
    neither the live DB nor the network is touched by these tests."""
    monkeypatch.setattr("api.routes.images.store_hosts", lambda db: HOSTS)
    app.dependency_overrides[get_db] = lambda: None
    limiter.reset()
    yield
    app.dependency_overrides.pop(get_db, None)


def _install_client(monkeypatch, *streams):
    fake = _FakeClient(list(streams))
    monkeypatch.setattr("api.routes.images.httpx.Client", lambda *a, **k: fake)
    return fake


client = TestClient(app, raise_server_exceptions=False)


def test_non_image_content_type_gives_placeholder(image_env, monkeypatch):
    _install_client(monkeypatch, _FakeStream(status_code=200, content_type="text/html",
                                              chunks=[b"<html>not an image</html>"]))
    resp = client.get("/api/v1/images", params={"u": "https://pcstudio.in/x.jpg"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")


def test_oversized_image_gives_placeholder_and_stops_reading_at_cap(image_env, monkeypatch):
    # 10 chunks of 1 MiB each = 10 MiB total, well past MAX_BYTES (5 MiB) -
    # the route must not read them all.
    chunk = b"a" * (1024 * 1024)
    stream = _FakeStream(status_code=200, content_type="image/png", chunks=[chunk] * 10)
    _install_client(monkeypatch, stream)
    resp = client.get("/api/v1/images", params={"u": "https://pcstudio.in/big.png"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    # Stopped at or just past the cap, nowhere near the full 10 MiB offered.
    assert MAX_BYTES < stream.bytes_read <= MAX_BYTES + len(chunk)


def test_small_image_is_passed_through(image_env, monkeypatch):
    body = b"0123456789"
    _install_client(monkeypatch, _FakeStream(status_code=200, content_type="image/png",
                                              chunks=[body]))
    resp = client.get("/api/v1/images", params={"u": "https://pcstudio.in/small.png"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content == body


def test_disallowed_redirect_hop_gives_placeholder(image_env, monkeypatch):
    redirect = _FakeStream(status_code=302, is_redirect=True, next_url="https://evil.example/x.jpg")
    _install_client(monkeypatch, redirect)
    resp = client.get("/api/v1/images", params={"u": "https://pcstudio.in/x.jpg"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")


def test_network_error_gives_placeholder(image_env, monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("boom")
    monkeypatch.setattr("api.routes.images.httpx.Client", _raise)
    resp = client.get("/api/v1/images", params={"u": "https://pcstudio.in/x.jpg"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
