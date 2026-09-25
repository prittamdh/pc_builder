"""SEC-07: save-build rejects an oversized selection count, an oversized
request body, and unknown product ids - all before anything is written.
SEC-03: builder routes and save-build carry their own (tighter) rate limits.

Every case uses a stubbed DB session (never the live database) and asserts
`add`/`commit` were never called when a request is rejected.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.deps import get_db
from api.main import app
from api.rate_limit import limiter
from configs import settings

client = TestClient(app)


class _StubSession:
    """A get_db stand-in. `found_ids` are the product ids that "exist" for
    the unknown-product-id check; add()/commit() are recorded, never executed
    against a real database."""

    def __init__(self, found_ids=()):
        self.added = []
        self.committed = False
        self._found_ids = set(found_ids)

    def scalars(self, stmt):
        found = self._found_ids

        class _Result:
            def __iter__(self_inner):
                return iter(SimpleNamespace(id=i) for i in found)

        return _Result()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        pass


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def stub_db():
    session = _StubSession()

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    yield session
    app.dependency_overrides.pop(get_db, None)


def test_too_many_selections_is_400_and_names_the_limit(stub_db):
    selections = {f"slot{i}": i for i in range(21)}
    resp = client.post("/api/v1/builder/builds", json={"selections": selections})
    assert resp.status_code == 400
    assert "20" in resp.json()["detail"]
    assert stub_db.added == []
    assert stub_db.committed is False


def test_oversized_body_is_413(stub_db):
    # A valid, small selections dict plus a very long notes field.
    body = {"selections": {"cpu": 1}, "notes": "x" * 20_000}
    assert len(json.dumps(body)) > 10_000
    resp = client.post("/api/v1/builder/builds", json=body)
    assert resp.status_code == 413
    assert stub_db.added == []
    assert stub_db.committed is False


def test_unknown_product_id_is_400(stub_db):
    # stub_db's found_ids is empty, so any product id looks unknown.
    resp = client.post("/api/v1/builder/builds", json={"selections": {"cpu": 999999}})
    assert resp.status_code == 400
    assert "Unknown product ids" in resp.json()["detail"]
    assert stub_db.added == []
    assert stub_db.committed is False


# --- SEC-03: builder and save-build rate limits ------------------------------

def test_third_validate_style_builder_request_is_429_json(monkeypatch):
    """/slots carries the same RATE_LIMIT_BUILDER limit as /validate, /candidates
    and GET /builds/{token}, with no DB or body needed - a clean way to prove
    the limit fires without depending on BuilderService's DB queries."""
    monkeypatch.setattr(settings, "RATE_LIMIT_BUILDER", "2/minute")
    assert client.get("/api/v1/builder/slots").status_code != 429
    assert client.get("/api/v1/builder/slots").status_code != 429
    resp = client.get("/api/v1/builder/slots")
    assert resp.status_code == 429
    assert resp.headers["content-type"].startswith("application/json")


def test_second_save_build_is_429_even_after_first_was_rejected(stub_db, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_SAVE_BUILD", "1/minute")
    # Empty selections -> 400, cheap and DB-free, but still counts against the limit.
    first = client.post("/api/v1/builder/builds", json={"selections": {}})
    assert first.status_code == 400
    second = client.post("/api/v1/builder/builds", json={"selections": {}})
    assert second.status_code == 429
    assert stub_db.added == []
    assert stub_db.committed is False
