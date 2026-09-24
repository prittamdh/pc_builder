"""SEC-02: the app refuses to start without an explicit DATABASE_URL.
Also covers ENV normalisation/validation (fails closed on typos, not open).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _run_without(env_key: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Boot api.main in a subprocess with dotenv disabled and env_key removed
    (plus any extra_env overrides applied on top)."""
    env = os.environ.copy()
    env.pop(env_key, None)
    if extra_env:
        env.update(extra_env)
    snippet = "import dotenv; dotenv.load_dotenv = lambda *a, **k: None; import api.main"
    return subprocess.run(
        [sys.executable, "-c", snippet],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_require_database_url_raises_when_none(monkeypatch):
    from configs import settings
    monkeypatch.setattr(settings, "DATABASE_URL", None)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        settings.require_database_url()


def test_require_database_url_raises_when_blank(monkeypatch):
    from configs import settings
    monkeypatch.setattr(settings, "DATABASE_URL", "   ")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        settings.require_database_url()


def test_app_refuses_to_start_without_database_url():
    """returncode != 0, the error names DATABASE_URL, and stderr never leaks a
    connection string (no "postgresql" substring anywhere in stderr)."""
    proc = _run_without("DATABASE_URL")
    assert proc.returncode != 0
    assert "DATABASE_URL" in proc.stderr
    assert "postgresql" not in proc.stderr


def test_env_typo_refuses_to_start_naming_env_and_allowed_values():
    """ENV=prod (not "production") must fail closed, not silently expose /docs."""
    proc = _run_without("ENV", extra_env={"ENV": "prod"})
    assert proc.returncode != 0
    assert "ENV" in proc.stderr
    assert "development" in proc.stderr
    assert "production" in proc.stderr


def test_env_padded_mixed_case_normalizes_to_production(monkeypatch):
    import importlib
    from configs import settings
    monkeypatch.setenv("ENV", " Production ")
    importlib.reload(settings)
    try:
        assert settings.ENV == "production"
    finally:
        monkeypatch.delenv("ENV", raising=False)
        importlib.reload(settings)


def test_env_unset_defaults_to_development(monkeypatch):
    import importlib
    from configs import settings
    monkeypatch.delenv("ENV", raising=False)
    importlib.reload(settings)
    assert settings.ENV == "development"
