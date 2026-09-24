import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dags"))
import scheduled_scraper_dag as dag  # noqa: E402


def test_recent_prices_are_fresh():
    now = datetime(2026, 9, 24, 12, 0)
    assert not dag.price_data_is_stale(now - timedelta(hours=2), now)


def test_day_old_prices_are_stale():
    now = datetime(2026, 9, 24, 12, 0)
    assert dag.price_data_is_stale(now - timedelta(hours=25), now)


def test_no_prices_at_all_is_stale():
    assert dag.price_data_is_stale(None, datetime(2026, 9, 24))
