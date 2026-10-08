"""The models must import under SQLAlchemy 1.4, which the Airflow image ships.

On 2026-09-25 three new models imported `mapped_column` from sqlalchemy.orm directly (a
2.0-only name). The DAG then failed to import inside Airflow, and server-side scraping
stopped for about 5.5 hours with nothing failing loudly: no task ran at all, so no task
could fail. Every model that uses the 2.0 names must fall back like the older ones do.
"""
import re
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "src" / "db" / "models"


def test_every_model_has_the_sqlalchemy_1_4_fallback():
    offenders = []
    for path in sorted(MODELS.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        bare = re.search(r"^from sqlalchemy\.orm import [^\n]*\b(mapped_column|Mapped|DeclarativeBase)\b", src, re.M)
        if bare and "except ImportError" not in src:
            offenders.append(path.name)
    assert offenders == [], f"2.0-only imports without the 1.4 fallback: {offenders}"
