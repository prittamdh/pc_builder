"""
Measure PostgreSQL size and price_history growth, and project 12 months forward.

Read-only. Never writes. The whole measurement runs inside SET TRANSACTION READ ONLY
(so a bug that tried to write would error, not silently commit) and ends with a
rollback, not a commit.

Prints:
  - total database size
  - the 10 largest tables by total relation size
  - price_history row count, min/max scraped_at, rows/day averaged over the last
    7 and 30 days, and bytes per row
  - distinct products with a price per day over the last 7 days (the size of a
    daily low/high rollup)
  - a 12-month projection for "keep everything" vs "90 days raw plus daily
    low/high", each checked against the 150 GB block volume (ROADMAP Phase 3)
  - with --dump-bytes N (a compressed pg_dump size measured by hand), a 12-month
    dump-size projection against the 20 GB (OCI Object Storage) and 10 GB (R2)
    free-tier budgets, per copy - how many copies to retain is 03-03's decision.

Usage:
    python scripts/measure_db_growth.py
    python scripts/measure_db_growth.py --dump-bytes 41943040

Measure a dump by hand first (read-only):
    docker exec pc_builder_postgres pg_dump -Fc -U pc_builder pc_builder | wc -c
"""
import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402

from db.session import SessionLocal  # noqa: E402

BLOCK_VOLUME_BYTES = 150 * 1024**3
OCI_OBJECT_STORAGE_BYTES = 20 * 1024**3
R2_BYTES = 10 * 1024**3

RETENTION_DAYS = 90
ROLLUP_DAYS_PROJECTED = 365


def project_growth(
    current_bytes: float,
    bytes_per_row: float,
    rows_per_day: float,
    days: int,
    retention_days: int | None,
    rollup_rows_per_day: float,
) -> float:
    """Project total bytes `days` from now.

    With retention_days=None, every row of the last `days` accumulates at
    rows_per_day. With retention_days set, only that many days of raw rows are kept;
    the rest of the period accrues rollup_rows_per_day instead (e.g. one low/high row
    per product per day instead of one row per scrape).
    """
    if rows_per_day == 0:
        return current_bytes

    if retention_days is None:
        raw_days = days
        rollup_days = 0
    else:
        raw_days = min(days, retention_days)
        rollup_days = max(0, days - retention_days)

    added_rows = rows_per_day * raw_days + rollup_rows_per_day * rollup_days
    return current_bytes + bytes_per_row * added_rows


def fits(projected_bytes: float, budget_bytes: float) -> bool:
    """True when the projection is within budget (equal counts as fitting)."""
    return projected_bytes <= budget_bytes


def _fmt_bytes(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def measure(session) -> dict:
    db_size = session.execute(
        text("SELECT pg_database_size(current_database())")
    ).scalar()

    largest_tables = session.execute(
        text(
            """
            SELECT relname, pg_total_relation_size(relid) AS total_bytes
            FROM pg_catalog.pg_statio_user_tables
            ORDER BY total_bytes DESC
            LIMIT 10
            """
        )
    ).all()

    total_rows, min_scraped, max_scraped = session.execute(
        text("SELECT count(*), min(scraped_at), max(scraped_at) FROM price_history")
    ).one()

    rows_last_7d = session.execute(
        text(
            "SELECT count(*) FROM price_history "
            "WHERE scraped_at >= now() - interval '7 days'"
        )
    ).scalar()
    rows_last_30d = session.execute(
        text(
            "SELECT count(*) FROM price_history "
            "WHERE scraped_at >= now() - interval '30 days'"
        )
    ).scalar()

    price_history_bytes = session.execute(
        text("SELECT pg_total_relation_size('price_history')")
    ).scalar()

    distinct_products_per_day_7d = session.execute(
        text(
            """
            SELECT count(*) FROM (
                SELECT DISTINCT date_trunc('day', scraped_at) AS d, product_id
                FROM price_history
                WHERE scraped_at >= now() - interval '7 days'
            ) t
            """
        )
    ).scalar()

    return {
        "db_size": db_size,
        "largest_tables": largest_tables,
        "total_rows": total_rows,
        "min_scraped": min_scraped,
        "max_scraped": max_scraped,
        "rows_per_day_7d": (rows_last_7d or 0) / 7,
        "rows_per_day_30d": (rows_last_30d or 0) / 30,
        "price_history_bytes": price_history_bytes,
        "bytes_per_row": (price_history_bytes / total_rows) if total_rows else 0,
        "rollup_rows_per_day": (distinct_products_per_day_7d or 0) / 7,
    }


def main(dump_bytes: int | None) -> None:
    with SessionLocal() as session:
        # Read-only for the whole measurement: a write anywhere in this transaction
        # would error instead of silently committing.
        session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            data = measure(session)
        finally:
            session.rollback()

    print("=" * 78)
    print("DB SIZE AND GROWTH (read-only)")
    print("=" * 78)
    print(f"Database size: {_fmt_bytes(data['db_size'])}")
    print()
    print("Largest tables:")
    for relname, total_bytes in data["largest_tables"]:
        print(f"  {relname:35s} {_fmt_bytes(total_bytes)}")
    print()
    print(
        f"price_history: {data['total_rows']} rows, "
        f"{data['min_scraped']} .. {data['max_scraped']}"
    )
    print(f"  rows/day (last 7d avg):  {data['rows_per_day_7d']:.1f}")
    print(f"  rows/day (last 30d avg): {data['rows_per_day_30d']:.1f}")
    print(f"  bytes/row: {data['bytes_per_row']:.1f}")
    print(
        f"  distinct products/day with a price (last 7d avg, rollup size): "
        f"{data['rollup_rows_per_day']:.1f}"
    )
    print()

    # Use the higher of the two averages (typically the more recent 7-day figure) as the
    # forward-looking rate: understating growth is the riskier mistake for capacity
    # planning, and the 30-day average is dragged down by an early, slower-scraping period.
    rows_per_day = max(data["rows_per_day_7d"], data["rows_per_day_30d"])

    keep_everything = project_growth(
        current_bytes=data["db_size"],
        bytes_per_row=data["bytes_per_row"],
        rows_per_day=rows_per_day,
        days=365,
        retention_days=None,
        rollup_rows_per_day=0,
    )
    with_retention = project_growth(
        current_bytes=data["db_size"],
        bytes_per_row=data["bytes_per_row"],
        rows_per_day=rows_per_day,
        days=365,
        retention_days=RETENTION_DAYS,
        rollup_rows_per_day=data["rollup_rows_per_day"],
    )

    print("12-month projection (against the 150 GB block volume):")
    print(
        f"  keep everything:            {_fmt_bytes(keep_everything)} "
        f"- fits: {fits(keep_everything, BLOCK_VOLUME_BYTES)}"
    )
    print(
        f"  {RETENTION_DAYS} days raw + daily low/high: {_fmt_bytes(with_retention)} "
        f"- fits: {fits(with_retention, BLOCK_VOLUME_BYTES)}"
    )
    print()

    if dump_bytes is not None:
        dump_growth_factor = keep_everything / data["db_size"] if data["db_size"] else 1
        projected_dump = dump_bytes * dump_growth_factor
        print(f"Measured dump size (per copy, today): {_fmt_bytes(dump_bytes)}")
        print(
            f"12-month projected dump size (per copy, keep-everything growth rate): "
            f"{_fmt_bytes(projected_dump)}"
        )
        print(
            f"  fits OCI Object Storage (20 GB) per copy: "
            f"{fits(projected_dump, OCI_OBJECT_STORAGE_BYTES)}"
        )
        print(f"  fits R2 (10 GB) per copy: {fits(projected_dump, R2_BYTES)}")
        print("  (how many copies to retain is decided in 03-03)")
    print("=" * 78)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dump-bytes",
        type=int,
        default=None,
        help="Size in bytes of a compressed pg_dump, measured by hand.",
    )
    args = parser.parse_args()
    main(args.dump_bytes)
