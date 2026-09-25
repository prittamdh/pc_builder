"""Pipeline checks that fail loudly (moved from dags/scheduled_scraper_dag.py in plan
02-03, so the worker never imports from dags/).

- OPS-05: per-store price freshness - names every store that stopped saving.
- OPS-06: canonical extraction made no progress while a backlog was waiting.
"""
from datetime import datetime, timedelta, timezone

from db.session import SessionLocal


# The p_category values the 9 canonical-identity extractors handle (matching each
# extractor's own where-clause, e.g. scripts/extract_gpu_titles_groq.py:34).
BACKLOG_CATEGORIES = (
    "CPU",
    "Motherboard",
    "GPU",
    "Storage",
    "Power Supply",
    "CPU Cooler",
    "Cabinet",
    "Monitor",
    "RAM",
)


def backlog_snapshot(session) -> dict[int, tuple[str | None, str]]:
    """Product id -> (canonical_id, spec_status) for every product still in the backlog
    (BACKLOG_CATEGORIES, canonical_id IS NULL). Read only."""
    from sqlalchemy import select
    from db.models.product import Product

    rows = session.execute(
        select(Product.id, Product.canonical_id, Product.spec_status)
        .where(Product.p_category.in_(BACKLOG_CATEGORIES), Product.canonical_id.is_(None))
    ).all()
    return {pid: (canonical_id, spec_status) for pid, canonical_id, spec_status in rows}


def state_of(session, ids) -> dict[int, tuple[str | None, str]]:
    """Re-reads (canonical_id, spec_status) for the given product ids. Read only."""
    from sqlalchemy import select
    from db.models.product import Product

    ids = list(ids)
    if not ids:
        return {}
    rows = session.execute(
        select(Product.id, Product.canonical_id, Product.spec_status)
        .where(Product.id.in_(ids))
    ).all()
    return {pid: (canonical_id, spec_status) for pid, canonical_id, spec_status in rows}


def count_extraction_progress(
    before: dict[int, tuple[str | None, str]],
    after: dict[int, tuple[str | None, str]],
) -> int:
    """Count of ids that moved forward: canonical_id became set, or spec_status changed
    to anything other than "failed". A row that only moves to "failed" is not progress."""
    progress = 0
    for pid, (before_canonical, before_status) in before.items():
        after_canonical, after_status = after.get(pid, (before_canonical, before_status))
        canonical_now_set = before_canonical is None and after_canonical is not None
        status_changed_not_to_failed = after_status != before_status and after_status != "failed"
        if canonical_now_set or status_changed_not_to_failed:
            progress += 1
    return progress


def check_extraction_progress(backlog_before: int, progress: int) -> None:
    """Raise when a cycle made zero progress while work was waiting. backlog_before == 0
    is not a failure - there was nothing to do."""
    if backlog_before > 0 and progress == 0:
        raise RuntimeError(
            f"0 extractions this cycle with a backlog of {backlog_before} - "
            "every provider may be exhausted."
        )


PRICE_MAX_AGE = timedelta(hours=24)


def price_data_is_stale(latest: datetime | None, now: datetime, max_age: timedelta = PRICE_MAX_AGE) -> bool:
    """True when no price has been saved within max_age (or ever)."""
    return latest is None or now - latest > max_age


def _as_naive_utc(value: datetime | None) -> datetime | None:
    """Normalize to naive UTC. A naive datetime is assumed to already be UTC (matching
    PriceHistory.scraped_at, saved via datetime.utcnow()). A tz-aware datetime is
    converted with astimezone(timezone.utc).replace(tzinfo=None) - never by blindly
    attaching a different tzinfo, which changes the instant a naive value represents
    instead of converting it."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def stale_stores(
    latest_by_store: dict[str, datetime | None],
    now: datetime,
    max_age: timedelta = PRICE_MAX_AGE,
) -> list[str]:
    """Names (sorted) of stores whose latest saved price is stale or missing.

    Reuses price_data_is_stale per store, comparing everything in naive UTC (see
    _as_naive_utc) so a naive `now` and a tz-aware `latest` (or vice versa, or both
    tz-aware in different zones) never raises TypeError and never mis-measures the real
    elapsed time by a timezone's UTC offset.
    """
    now_utc = _as_naive_utc(now)
    stale = []
    for name, latest in latest_by_store.items():
        latest_utc = _as_naive_utc(latest)
        if price_data_is_stale(latest_utc, now_utc, max_age):
            stale.append(name)
    return sorted(stale)


def format_stale_message(stale: list[tuple[str, datetime | None]]) -> str:
    """Human-readable message naming every stale store and when it last saved a price."""
    parts = [f"{name} (last: {latest if latest is not None else 'never'})" for name, latest in stale]
    return f"No price saved in 24h for: {', '.join(parts)}"


def latest_price_by_store(session) -> dict[str, datetime | None]:
    """Latest PriceHistory.scraped_at per active store (None if the store has none).

    One query: active stores, left-outer-joined to Product (Product.sid == Store.id) and
    to PriceHistory (PriceHistory.product_id == Product.id), grouped by store. Read only.
    """
    from sqlalchemy import func, select
    from db.models.store import Store
    from db.models.product import Product
    from db.models.price_history import PriceHistory

    rows = session.execute(
        select(Store.display_name, func.max(PriceHistory.scraped_at))
        .select_from(Store)
        .outerjoin(Product, Product.sid == Store.id)
        .outerjoin(PriceHistory, PriceHistory.product_id == Product.id)
        .where(Store.active == True)  # noqa: E712
        .group_by(Store.display_name)
    ).all()
    return {name: latest for name, latest in rows}


def check_price_freshness():
    """Fail loudly when prices stop arriving, naming every store that stopped saving.

    Scraping once stopped for five weeks with every run marked success: the scheduler was
    down for a month, then every save raised a TypeError that was caught and printed. The
    all-targets-failed check covers the second case; this covers everything else that
    leaves the catalog quietly frozen - no targets coming due, one store changing its
    markup so its pages parse to nothing, saves that succeed but write no price rows.
    """
    with SessionLocal() as session:
        latest_by_store = latest_price_by_store(session)

    # Naive UTC, matching PriceHistory.scraped_at (datetime.utcnow()) - never local
    # wall-clock time, or a worker running outside UTC (e.g. IST) would flag every store
    # stale hours early (or late).
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_names = set(stale_stores(latest_by_store, now))
    if stale_names:
        stale_pairs = [(name, latest_by_store[name]) for name in sorted(stale_names)]
        raise RuntimeError(format_stale_message(stale_pairs))
    for name, latest in latest_by_store.items():
        print(f"[Freshness] {name}: latest price saved at {latest}")
