"""Shared fixtures for tests that must reload configs.settings/api.main after
changing env vars (ENV, CORS_ALLOWED_ORIGINS, ...). A bare `monkeypatch.setenv`
does not re-run the module-level code in settings.py/main.py that reads the
env var, so tests that need a fresh app import must reload both modules - and
must do so in fixture teardown (not as the last line of the test body) so a
failed assertion doesn't leave the reloaded, env-specific state behind for
later tests.
"""
import importlib

import pytest


@pytest.fixture
def app_with_env(monkeypatch):
    """Yields a builder function: call it with env var kwargs to get a fresh
    `api.main.app` built under those env vars. Always restores configs.settings
    and api.main to their unset-env (development/default) state afterward,
    even if the test raises.
    """
    touched_keys: set[str] = set()

    def _build(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
            touched_keys.add(key)
        from configs import settings
        importlib.reload(settings)
        from api import main
        importlib.reload(main)
        return main.app

    yield _build

    for key in touched_keys:
        monkeypatch.delenv(key, raising=False)
    from configs import settings
    importlib.reload(settings)
    from api import main
    importlib.reload(main)


@pytest.fixture(scope="session")
def scratch_engine():
    """An engine on a throwaway Postgres schema holding every table in the models.

    Queue tests need real Postgres (row locks, SKIP LOCKED, partial unique indexes)
    but must never touch the live catalog, so they get their own schema in the same
    database, dropped at the end of the session.
    """
    import uuid

    from sqlalchemy import create_engine, text

    import db.models  # noqa: F401  (registers every table on Base.metadata)
    from db.base import Base
    from db.connection import engine as live_engine

    schema = f"test_{uuid.uuid4().hex[:10]}"
    with live_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        live_engine.url,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_size=10,
    )
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        with live_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.fixture
def scratch_sessions(scratch_engine):
    """A sessionmaker on the scratch schema, emptied before each test."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    with scratch_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE scrape_jobs, scrape_agents, pipeline_runs, price_history, "
            "products, scrape_targets, stores RESTART IDENTITY CASCADE"
        ))
    return sessionmaker(bind=scratch_engine, autoflush=False, expire_on_commit=False)
