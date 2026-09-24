"""SEC-06: API docs and schema must be hidden when ENV=production."""
from fastapi.testclient import TestClient


def test_docs_are_404_in_production(app_with_env):
    app = app_with_env(ENV="production")
    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_are_200_by_default(app_with_env, monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    app = app_with_env()
    client = TestClient(app)
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_no_agent_path_in_dev_openapi_schema(app_with_env, monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    app = app_with_env()
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    for path in schema.get("paths", {}):
        assert not path.startswith("/api/agent")


def test_padded_mixed_case_production_is_normalized(app_with_env):
    """ENV=" Production " (stray whitespace/casing) is still treated as production."""
    app = app_with_env(ENV=" Production ")
    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
