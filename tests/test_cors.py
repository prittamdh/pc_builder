"""SEC-01: CORS must not trust every origin, and must never send credentials."""
from fastapi.testclient import TestClient


def test_unlisted_origin_gets_no_acao_header(app_with_env):
    app = app_with_env(CORS_ALLOWED_ORIGINS="https://allowed.example")
    client = TestClient(app)
    resp = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}


def test_preflight_from_unlisted_origin_gets_no_acao_header(app_with_env):
    app = app_with_env(CORS_ALLOWED_ORIGINS="https://allowed.example")
    client = TestClient(app)
    resp = client.options(
        "/api/v1/builder/validate",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}


def test_listed_origin_is_echoed_back(app_with_env):
    app = app_with_env(CORS_ALLOWED_ORIGINS="https://allowed.example")
    client = TestClient(app)
    resp = client.get("/health", headers={"Origin": "https://allowed.example"})
    assert resp.headers.get("access-control-allow-origin") == "https://allowed.example"


def test_credentials_never_allowed(app_with_env):
    app = app_with_env(CORS_ALLOWED_ORIGINS="https://allowed.example")
    client = TestClient(app)
    resp = client.get("/health", headers={"Origin": "https://allowed.example"})
    assert resp.headers.get("access-control-allow-credentials") != "true"
