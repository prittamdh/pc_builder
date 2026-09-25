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
