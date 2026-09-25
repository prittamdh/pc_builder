"""SEC-02: the app refuses to start without an explicit DATABASE_URL.
Also covers ENV normalisation/validation (fails closed on typos, not open).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_FAKE_DATABASE_URL = "postgresql+psycopg://user:password@host:5432/pc_builder"


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


def _reload_settings_with(monkeypatch, **env_values):
    """Reload configs.settings with the given env vars set (value None means
    delete the var) and dotenv disabled, restoring the previous module state
    afterward. Returns the freshly reloaded settings module."""
    import importlib
    from configs import settings

    for key, value in env_values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    importlib.reload(settings)
    return settings


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


# --- F2: a blank env value must mean "use the default", not crash or silently
# --- change behaviour (e.g. RATE_LIMIT_ENABLED= must not become False). -----

def test_blank_env_uses_default_development(monkeypatch):
    settings = _reload_settings_with(monkeypatch, ENV="")
    assert settings.ENV == "development"


def test_blank_request_timeout_uses_default(monkeypatch):
    settings = _reload_settings_with(monkeypatch, REQUEST_TIMEOUT="")
    assert settings.REQUEST_TIMEOUT == 20


def test_blank_max_retries_uses_default(monkeypatch):
    settings = _reload_settings_with(monkeypatch, MAX_RETRIES="")
    assert settings.MAX_RETRIES == 3


def test_blank_backoff_factor_uses_default(monkeypatch):
    settings = _reload_settings_with(monkeypatch, BACKOFF_FACTOR="")
    assert settings.RETRY_BACKOFF == 2


def test_blank_fuzzy_match_threshold_uses_default(monkeypatch):
    settings = _reload_settings_with(monkeypatch, FUZZY_MATCH_THRESHOLD="")
    assert settings.FUZZY_MATCH_THRESHOLD == 0.90


def test_blank_rate_limit_enabled_defaults_to_true(monkeypatch):
    """The reviewer's finding: RATE_LIMIT_ENABLED="" must not silently become
    False (which would turn off all rate limiting) - blank means default."""
    settings = _reload_settings_with(monkeypatch, RATE_LIMIT_ENABLED="")
    assert settings.RATE_LIMIT_ENABLED is True


def test_blank_trust_cf_connecting_ip_defaults_to_false(monkeypatch):
    settings = _reload_settings_with(monkeypatch, TRUST_CF_CONNECTING_IP="")
    assert settings.TRUST_CF_CONNECTING_IP is False


def test_blank_rate_limit_default_uses_default_string(monkeypatch):
    settings = _reload_settings_with(monkeypatch, RATE_LIMIT_DEFAULT="")
    assert settings.RATE_LIMIT_DEFAULT == "300/minute"


def test_blank_rate_limit_images_uses_default_string(monkeypatch):
    settings = _reload_settings_with(monkeypatch, RATE_LIMIT_IMAGES="")
    assert settings.RATE_LIMIT_IMAGES == "120/minute"


def test_blank_rate_limit_builder_uses_default_string(monkeypatch):
    settings = _reload_settings_with(monkeypatch, RATE_LIMIT_BUILDER="")
    assert settings.RATE_LIMIT_BUILDER == "60/minute"


def test_blank_rate_limit_save_build_uses_default_string(monkeypatch):
    settings = _reload_settings_with(monkeypatch, RATE_LIMIT_SAVE_BUILD="")
    assert settings.RATE_LIMIT_SAVE_BUILD == "10/minute"


def test_invalid_rate_limit_enabled_value_raises_naming_variable(monkeypatch):
    with pytest.raises(RuntimeError, match="RATE_LIMIT_ENABLED"):
        _reload_settings_with(monkeypatch, RATE_LIMIT_ENABLED="maybe")


def test_invalid_trust_cf_connecting_ip_value_raises_naming_variable(monkeypatch):
    with pytest.raises(RuntimeError, match="TRUST_CF_CONNECTING_IP"):
        _reload_settings_with(monkeypatch, TRUST_CF_CONNECTING_IP="yes")


def test_invalid_rate_limit_default_string_raises_naming_variable(monkeypatch):
    """RATE_LIMIT_DEFAULT is validated eagerly at import with
    limits.parse_many, so a typo fails closed at startup rather than 500ing
    every request at call time."""
    with pytest.raises(RuntimeError, match="RATE_LIMIT_DEFAULT"):
        _reload_settings_with(monkeypatch, RATE_LIMIT_DEFAULT="not-a-limit")


def test_invalid_rate_limit_images_string_raises_naming_variable(monkeypatch):
    with pytest.raises(RuntimeError, match="RATE_LIMIT_IMAGES"):
        _reload_settings_with(monkeypatch, RATE_LIMIT_IMAGES="lots per whenever")


def test_env_example_with_only_database_url_boots_with_rate_limiting_enabled(tmp_path):
    """End-to-end: a fresh copy of .env.example, with only DATABASE_URL
    filled in (every other key stays blank, as shipped), must boot the app
    with rate limiting enabled and a healthy /health - not crash, and not
    silently disable rate limiting."""
    env_example = ROOT / ".env.example"
    content = env_example.read_text(encoding="utf-8")
    assert "DATABASE_URL=<postgresql+psycopg://user:password@host:5432/pc_builder>" in content
    content = content.replace(
        "DATABASE_URL=<postgresql+psycopg://user:password@host:5432/pc_builder>",
        f"DATABASE_URL={_FAKE_DATABASE_URL}",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")

    snippet = (
        "import dotenv; "
        f"dotenv.load_dotenv({str(env_file)!r}, override=True); "
        "import api.main as m; "
        "from starlette.testclient import TestClient; "
        "c = TestClient(m.app); "
        "r = c.get('/health'); "
        "print('STATUS', r.status_code); "
        "print('ENABLED', m.limiter.enabled)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "STATUS 200" in proc.stdout, proc.stdout + proc.stderr
    assert "ENABLED True" in proc.stdout, proc.stdout + proc.stderr
