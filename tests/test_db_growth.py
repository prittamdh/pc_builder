import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import measure_db_growth as m  # noqa: E402


def test_project_growth_no_retention_is_linear():
    assert m.project_growth(
        current_bytes=100, bytes_per_row=10, rows_per_day=5, days=365,
        retention_days=None, rollup_rows_per_day=0,
    ) == 100 + 10 * 5 * 365


def test_project_growth_with_retention_caps_raw_and_adds_rollup():
    days = 365
    retention_days = 90
    bytes_per_row = 10
    rows_per_day = 5
    rollup_rows_per_day = 2
    current_bytes = 100

    raw_days = min(days, retention_days)
    rollup_days = max(0, days - retention_days)
    expected = current_bytes + bytes_per_row * (
        rows_per_day * raw_days + rollup_rows_per_day * rollup_days
    )
    assert m.project_growth(
        current_bytes=current_bytes,
        bytes_per_row=bytes_per_row,
        rows_per_day=rows_per_day,
        days=days,
        retention_days=retention_days,
        rollup_rows_per_day=rollup_rows_per_day,
    ) == expected


def test_fits_true_when_equal():
    assert m.fits(100, 100) is True


def test_fits_false_when_one_byte_over():
    assert m.fits(101, 100) is False


def test_project_growth_zero_rows_per_day_returns_current_bytes_unchanged():
    assert m.project_growth(
        current_bytes=12345, bytes_per_row=10, rows_per_day=0, days=365,
        retention_days=None, rollup_rows_per_day=0,
    ) == 12345
