import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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


def test_exactly_24h_is_fresh():
    now = datetime(2026, 9, 24, 12, 0)
    assert not dag.price_data_is_stale(now - timedelta(hours=24), now)


def test_24h_plus_1s_is_stale():
    now = datetime(2026, 9, 24, 12, 0)
    assert dag.price_data_is_stale(now - timedelta(hours=24, seconds=1), now)


# --- stale_stores ---------------------------------------------------------

def test_stale_stores_returns_sorted_names_of_stale_stores():
    now = datetime(2026, 9, 24, 12, 0)
    latest_by_store = {
        "A": now - timedelta(hours=2),
        "B": now - timedelta(hours=25),
        "C": None,
    }
    assert dag.stale_stores(latest_by_store, now) == ["B", "C"]


def test_stale_stores_empty_dict_gives_empty_list():
    assert dag.stale_stores({}, datetime(2026, 9, 24)) == []


def test_stale_stores_tz_aware_latest_with_naive_now_no_typeerror():
    # naive_now is treated as already-UTC (matching how check_price_freshness builds it:
    # datetime.now(timezone.utc).replace(tzinfo=None)); tz_aware_latest is 2h before that
    # same UTC instant, so no TypeError and the store is fresh.
    tz_aware_latest = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)
    naive_now = datetime(2026, 9, 24, 12, 0)
    result = dag.stale_stores({"A": tz_aware_latest}, naive_now)
    assert result == []


def test_stale_stores_same_instant_different_timezones_stays_fresh():
    """A store scraped 23h ago in UTC is not stale even when 'now' is expressed in a
    different time zone (e.g. a worker process running in IST) representing the exact
    same real instant. Blindly attaching now's tzinfo to itself (the old bug) would
    shift the apparent gap by the zone's UTC offset (+5:30 for IST) and wrongly report
    28.5h - stale. Converting both sides to naive UTC keeps the true 23h gap - fresh."""
    latest_utc = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    true_now_utc_instant = latest_utc + timedelta(hours=23)
    ist = timezone(timedelta(hours=5, minutes=30))
    now_in_ist = true_now_utc_instant.astimezone(ist)

    assert dag.stale_stores({"A": latest_utc}, now_in_ist) == []


def test_stale_stores_fresh_stores_not_named():
    now = datetime(2026, 9, 24, 12, 0)
    latest_by_store = {"A": now - timedelta(hours=2)}
    assert dag.stale_stores(latest_by_store, now) == []


# --- format_stale_message --------------------------------------------------

def test_format_stale_message_contains_names_and_never():
    msg = dag.format_stale_message([("B", datetime(2026, 9, 23, 10, 0)), ("C", None)])
    assert "B" in msg
    assert "C" in msg
    assert "never" in msg


# --- latest_price_by_store / check_price_freshness (pure-function behavior) --

def _fixed_datetime_class(fixed_now):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now.replace(tzinfo=tz) if tz else fixed_now

    return _FixedDatetime


class _FakeSessionCtx:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


def test_check_price_freshness_raises_with_stale_store_name(monkeypatch):
    now = datetime(2026, 9, 24, 12, 0)
    latest_by_store = {
        "Fresh Store": now - timedelta(hours=1),
        "Stale Store": now - timedelta(hours=48),
        "Never Store": None,
    }
    monkeypatch.setattr(dag, "latest_price_by_store", lambda session: latest_by_store)
    monkeypatch.setattr(dag, "SessionLocal", lambda: _FakeSessionCtx())
    monkeypatch.setattr(dag, "datetime", _fixed_datetime_class(now))
    with pytest.raises(RuntimeError) as exc_info:
        dag.check_price_freshness()
    msg = str(exc_info.value)
    assert "Stale Store" in msg
    assert "Never Store" in msg
    assert "Fresh Store" not in msg


def test_check_price_freshness_idempotent_when_all_fresh(monkeypatch):
    now = datetime(2026, 9, 24, 12, 0)
    latest_by_store = {"Fresh Store": now - timedelta(hours=1)}
    monkeypatch.setattr(dag, "latest_price_by_store", lambda session: latest_by_store)
    monkeypatch.setattr(dag, "SessionLocal", lambda: _FakeSessionCtx())
    monkeypatch.setattr(dag, "datetime", _fixed_datetime_class(now))
    dag.check_price_freshness()
    dag.check_price_freshness()


# --- count_extraction_progress / check_extraction_progress (OPS-06) --------

def test_count_extraction_progress_counts_canonical_id_set():
    before = {1: (None, "pending"), 2: (None, "pending")}
    after = {1: ("k1", "extracted"), 2: (None, "pending")}
    assert dag.count_extraction_progress(before, after) == 1


def test_count_extraction_progress_failed_status_does_not_count():
    before = {1: (None, "pending")}
    after = {1: (None, "failed")}
    assert dag.count_extraction_progress(before, after) == 0


def test_count_extraction_progress_canonical_id_set_counts_even_if_status_unchanged():
    before = {1: (None, "pending")}
    after = {1: ("k1", "pending")}
    assert dag.count_extraction_progress(before, after) == 1


def test_count_extraction_progress_empty_before_gives_zero():
    assert dag.count_extraction_progress({}, {}) == 0


def test_check_extraction_progress_raises_naming_backlog_size():
    with pytest.raises(RuntimeError) as exc_info:
        dag.check_extraction_progress(5, 0)
    assert "5" in str(exc_info.value)


def test_check_extraction_progress_passes_with_progress():
    dag.check_extraction_progress(5, 1)


def test_check_extraction_progress_passes_with_zero_backlog():
    dag.check_extraction_progress(0, 0)


# --- execute_canonical_extraction_checked (OPS-06 wiring) -------------------

def test_execute_canonical_extraction_checked_defaults_to_15(monkeypatch):
    """The DAG calls execute_canonical_extraction_checked() with no arguments; it must
    not silently cut the underlying limit_per_category=15 default down to 10."""
    captured = {}

    def fake_execute_canonical_extraction(limit_per_category=None):
        captured["limit_per_category"] = limit_per_category

    monkeypatch.setattr(dag, "backlog_snapshot", lambda session: {})
    monkeypatch.setattr(dag, "state_of", lambda session, ids: {})
    monkeypatch.setattr(dag, "execute_canonical_extraction", fake_execute_canonical_extraction)
    monkeypatch.setattr(dag, "SessionLocal", lambda: _FakeSessionCtx())

    dag.execute_canonical_extraction_checked()

    assert captured["limit_per_category"] == 15


def test_execute_canonical_extraction_checked_passes_explicit_limit(monkeypatch):
    captured = {}

    def fake_execute_canonical_extraction(limit_per_category=None):
        captured["limit_per_category"] = limit_per_category

    monkeypatch.setattr(dag, "backlog_snapshot", lambda session: {})
    monkeypatch.setattr(dag, "state_of", lambda session, ids: {})
    monkeypatch.setattr(dag, "execute_canonical_extraction", fake_execute_canonical_extraction)
    monkeypatch.setattr(dag, "SessionLocal", lambda: _FakeSessionCtx())

    dag.execute_canonical_extraction_checked(limit_per_category=3)

    assert captured["limit_per_category"] == 3


def test_execute_canonical_extraction_checked_raises_when_runner_makes_no_progress(monkeypatch):
    """Snapshot has one backlog product; the (fake) runner does nothing; the re-read
    session sees the same unchanged state, so 0 progress against a backlog of 1 must
    raise."""
    snapshot = {1: (None, "pending")}

    monkeypatch.setattr(dag, "backlog_snapshot", lambda session: dict(snapshot))
    monkeypatch.setattr(dag, "state_of", lambda session, ids: dict(snapshot))
    monkeypatch.setattr(dag, "execute_canonical_extraction", lambda limit_per_category=None: None)
    monkeypatch.setattr(dag, "SessionLocal", lambda: _FakeSessionCtx())

    with pytest.raises(RuntimeError) as exc_info:
        dag.execute_canonical_extraction_checked()
    assert "1" in str(exc_info.value)


# --- pipeline_failed_guard (makes a partially-failed DagRun state failed) ---

def test_pipeline_failed_guard_raises():
    with pytest.raises(RuntimeError):
        dag.pipeline_failed_guard()
