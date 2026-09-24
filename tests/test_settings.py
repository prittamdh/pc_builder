"""SEC-02: the app refuses to start without an explicit DATABASE_URL."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def test_require_database_url_raises_when_none(monkeypatch):
    sys.path.insert(0, str(SRC))
    import importlib
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
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    snippet = (
        "import dotenv; dotenv.load_dotenv = lambda *a, **k: None; "
        "import sys; sys.path.insert(0, r'" + str(SRC) + "'); "
        "import api.main"
    )
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode != 0
    assert "DATABASE_URL" in proc.stderr


def test_refuse_to_start_stderr_has_no_connection_string():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    snippet = (
        "import dotenv; dotenv.load_dotenv = lambda *a, **k: None; "
        "import sys; sys.path.insert(0, r'" + str(SRC) + "'); "
        "import api.main"
    )
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "postgresql" not in proc.stderr
