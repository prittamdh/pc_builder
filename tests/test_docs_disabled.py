"""SEC-06: API docs and schema must be hidden when ENV=production."""
import importlib

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
    monkeypatch.delenv("ENV", raising=False)
    from configs import settings
    importlib.reload(settings)
    from api import main
    importlib.reload(main)


def test_docs_are_404_in_production(monkeypatch):
    app = _reload_app_with_env(monkeypatch, ENV="production")
    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    _teardown(monkeypatch)


def test_docs_are_200_by_default(monkeypatch):
    app = _reload_app_with_env(monkeypatch)
    client = TestClient(app)
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    _teardown(monkeypatch)


def test_no_agent_path_in_dev_openapi_schema(monkeypatch):
    app = _reload_app_with_env(monkeypatch)
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    for path in schema.get("paths", {}):
        assert not path.startswith("/api/agent")
    _teardown(monkeypatch)
