"""
db.connection must fail closed with a clear message when DATABASE_URL is unset,
instead of letting create_engine(None, ...) raise an opaque TypeError. No live DB:
DATABASE_URL is monkeypatched, never a real connection made.
"""
import importlib
import sys

import pytest

import configs.settings as settings


@pytest.fixture(autouse=True)
def _clean_db_connection_cache():
    """Ensure db.connection is freshly imported for each test in this file, and leave
    no monkeypatched (broken) module cached for tests outside this file afterward."""
    sys.modules.pop("db.connection", None)
    yield
    sys.modules.pop("db.connection", None)
    # Re-import once more with real settings restored (monkeypatch is already undone
    # by the time this fixture's teardown runs), so later tests/modules that do
    # `from db.connection import engine` get a good module, not a cached failure.
    importlib.import_module("db.connection")


def test_missing_database_url_raises_clear_runtime_error(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", None)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        importlib.import_module("db.connection")


def test_blank_database_url_raises_clear_runtime_error(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "   ")

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        importlib.import_module("db.connection")


def test_missing_database_url_is_not_a_typeerror(monkeypatch):
    """Before this fix, create_engine(None, ...) raised a low-level TypeError/
    ArgumentError with no mention of DATABASE_URL - the whole point of the fix."""
    monkeypatch.setattr(settings, "DATABASE_URL", None)

    with pytest.raises(RuntimeError):
        importlib.import_module("db.connection")


def test_set_database_url_builds_an_engine_without_error(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/db")

    module = importlib.import_module("db.connection")

    assert module.engine is not None
