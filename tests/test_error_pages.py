"""WEB-01/WEB-02: branded 404/500 pages for the browser, JSON 404/500 for the
API, and no traceback/framework leakage in either. Uses TestClient directly
against api.main.app (no live-server subprocess needed for these).
"""
from fastapi import HTTPException
from starlette.testclient import TestClient

from api.deps import get_db
from api.main import app


def _no_db():
    """A get_db override that always reports 'no row found', so the 404 path
    is exercised without needing a real database connection."""
    class _EmptySession:
        def scalar(self, *a, **k):
            return None

        def scalars(self, *a, **k):
            class _Empty:
                def all(self):
                    return []
            return _Empty()

    yield _EmptySession()


client = TestClient(app, raise_server_exceptions=False)


def test_unknown_page_returns_branded_404_html():
    resp = client.get("/no-such-page")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("text/html")
    assert 'href="/"' in resp.text


def test_unknown_api_path_returns_json_404():
    resp = client.get("/api/v1/no-such-thing")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert "detail" in resp.json()


def test_unknown_share_token_stays_json_404_and_skips_db():
    app.dependency_overrides[get_db] = _no_db
    try:
        resp = client.get("/api/v1/builder/builds/zzzz-unknown")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert "detail" in resp.json()


def _install_crash_routes():
    @app.get("/__test_crash_page", include_in_schema=False)
    def _crash_page():
        raise RuntimeError("secret-boom")

    @app.get("/api/v1/__test_crash_api", include_in_schema=False)
    def _crash_api():
        raise RuntimeError("secret-boom")


def _remove_crash_routes():
    app.router.routes = [
        r for r in app.router.routes
        if getattr(r, "path", None) not in ("/__test_crash_page", "/api/v1/__test_crash_api")
    ]


def test_page_route_crash_returns_generic_500_html_no_internals():
    _install_crash_routes()
    try:
        resp = client.get("/__test_crash_page")
        assert resp.status_code == 500
        assert resp.headers["content-type"].startswith("text/html")
        body = resp.text
        for leak in ("Traceback", "secret-boom", 'File "', "starlette", "fastapi"):
            assert leak not in body
    finally:
        _remove_crash_routes()


def test_api_route_crash_returns_generic_500_json():
    _install_crash_routes()
    try:
        resp = client.get("/api/v1/__test_crash_api")
        assert resp.status_code == 500
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json() == {"detail": "Internal server error."}
    finally:
        _remove_crash_routes()


def test_error_pages_carry_security_headers():
    resp = client.get("/no-such-page")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert "content-security-policy" in resp.headers
