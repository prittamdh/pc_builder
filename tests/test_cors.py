"""SEC-01: CORS must not trust every origin, and must never send credentials."""
import importlib
import os

from fastapi.testclient import TestClient


def _reload_app_with_env(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from configs import settings
    importlib.reload(settings)
    from api import main
    importlib.reload(main)
    return main.app


def _teardown(monkeypatch):
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    from configs import settings
    importlib.reload(settings)
    from api import main
    importlib.reload(main)


def test_unlisted_origin_gets_no_acao_header(monkeypatch):
    app = _reload_app_with_env(monkeypatch, CORS_ALLOWED_ORIGINS="https://allowed.example")
    client = TestClient(app)
    resp = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}
    _teardown(monkeypatch)


def test_preflight_from_unlisted_origin_gets_no_acao_header(monkeypatch):
    app = _reload_app_with_env(monkeypatch, CORS_ALLOWED_ORIGINS="https://allowed.example")
    client = TestClient(app)
    resp = client.options(
        "/api/v1/builder/validate",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}
    _teardown(monkeypatch)


def test_listed_origin_is_echoed_back(monkeypatch):
    app = _reload_app_with_env(monkeypatch, CORS_ALLOWED_ORIGINS="https://allowed.example")
    client = TestClient(app)
    resp = client.get("/health", headers={"Origin": "https://allowed.example"})
    assert resp.headers.get("access-control-allow-origin") == "https://allowed.example"
    _teardown(monkeypatch)


def test_credentials_never_allowed(monkeypatch):
    app = _reload_app_with_env(monkeypatch, CORS_ALLOWED_ORIGINS="https://allowed.example")
    client = TestClient(app)
    resp = client.get("/health", headers={"Origin": "https://allowed.example"})
    assert resp.headers.get("access-control-allow-credentials") != "true"
    _teardown(monkeypatch)
