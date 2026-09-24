from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

# Ensure src/ is on sys.path
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from db.session import SessionLocal
from scrapers.generic_scraper import GenericScraper
from scrapers.http_client import HttpClient
from services.scrape_target_service import ScrapeTargetService
from services.search_service import SearchService
from services.store_service import StoreService
from common.enums.target_type import TargetType


def execute_due_scrape_targets(limit: int = 10, max_pages: int = 2):
    """Polls and executes due scrape targets across active stores."""
    with SessionLocal() as session:
        target_service = ScrapeTargetService(session)
        store_service = StoreService(session)
        search_service = SearchService(session)

        due_targets = target_service.get_due_targets(limit=limit)
        print(f"[Scheduled Scraper] Found {len(due_targets)} due targets to process.")

        if not due_targets:
            return

        attempted = failed = 0
        with HttpClient() as client:
            for target in due_targets:
                store = store_service.get(target.store_id)
                if not store or not store.active:
                    continue

                print(f"[Scheduled Scraper] Scraping target '{target.target_value}' on {store.display_name}")

                target_val = str(target.target_value)
                attempted += 1
                try:
                    scraper = GenericScraper(client, store)

                    # target_type is a TargetType enum value (SEARCH=0, CATEGORY=1, PRODUCT=2,
                    # CUSTOM_URL=3). Previously this compared against 2 (PRODUCT) instead of 1
                    # (CATEGORY), so ~87% of targets - all correctly tagged CATEGORY - were
                    # incorrectly routed through search-query scraping.
                    is_category = target.target_type == int(TargetType.CATEGORY)
                    target_max_pages = target.schedule_config.get("max_pages", max_pages) if isinstance(target.schedule_config, dict) else max_pages
                    hard_category = target.schedule_config.get("category") if isinstance(target.schedule_config, dict) else None

                    if is_category:
                        results = scraper.scrape_category_all_pages(
                            endpoint=target.target_value,
                            max_pages=target_max_pages,
                        )
                    else:
                        results = scraper.scrape_search_all_pages(
                            query=target.target_value,
                            max_pages=max_pages,
                        )

                    if results:
                        search_service.save_many(results, target_id=target.id, hard_category=hard_category)
                        print(f"[Scheduled Scraper] Saved {len(results)} products for '{target_val}' (target_id={target.id}, category={hard_category})")

                    target_service.mark_scraped(target)

                except Exception as e:
                    session.rollback()
                    failed += 1
                    print(f"[Scheduled Scraper Error] Failed scraping target '{target_val}': {e}")

        # One bad target shouldn't sink the run, but every target failing is a broken
        # pipeline. Catching per target once hid a TypeError for weeks: each run was
        # marked success while no price was saved.
        if attempted and failed == attempted:
            raise RuntimeError(f"All {attempted} scrape targets failed - see errors above.")


def execute_canonical_extraction(limit_per_category: int = 15):
    """Runs incremental LLM-based canonical identity extraction (Mistral) for newly-scraped
    products across all 9 tracked categories. Each extractor already defaults to processing
    only products missing a canonical_id, so this is safe to run every DAG cycle without
    reprocessing existing work or overrunning the free-tier rate limit (~9 categories x a
    couple of small batches per run, well under Mistral's 50 RPM)."""
    scripts_path = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    from extract_cpu_titles_groq import extract_cpu_identity
    from extract_motherboard_titles_groq import extract_motherboard_identity
    from extract_gpu_titles_groq import extract_gpu_identity
    from extract_storage_titles_groq import extract_storage_identity
    from extract_psu_titles_groq import extract_psu_identity
    from extract_cooler_titles_groq import extract_cooler_identity
    from extract_cabinet_titles_groq import extract_cabinet_identity
    from extract_monitor_titles_groq import extract_monitor_identity
    from extract_ram_titles_groq import extract_ram_titles
    from wire_ram_canonical import wire_ram_canonical

    runners = [
        ("CPU", extract_cpu_identity),
        ("Motherboard", extract_motherboard_identity),
        ("GPU", extract_gpu_identity),
        ("Storage", extract_storage_identity),
        ("Power Supply", extract_psu_identity),
        ("CPU Cooler", extract_cooler_identity),
        ("Cabinet", extract_cabinet_identity),
        ("Monitor", extract_monitor_identity),
    ]

    for label, fn in runners:
        try:
            fn(limit=limit_per_category)
        except Exception as e:
            print(f"[Canonical Extraction] {label} failed: {e}")

    try:
        extract_ram_titles(limit=limit_per_category)
        wire_ram_canonical()
    except Exception as e:
        print(f"[Canonical Extraction] RAM failed: {e}")


def execute_physical_spec_extraction(limit_per_category: int = 10):
    """Stage 2: fill physical specs for canonical models that don't have them yet.

    Runs after identity extraction, since every one of these keys off canonical_id.
    Each extractor skips models that already have a spec row, so a steady-state cycle
    does almost nothing; the small per-category limit keeps a burst of newly-scraped
    products from overrunning Mistral's free tier.

    RAM and Storage need no API calls at all - their identity extraction already
    captures everything their spec tables hold - so they run unlimited.
    """
    scripts_path = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    from extract_cpu_specs_groq import extract_cpu_specs
    from extract_monitor_specs_groq import extract_monitor_specs
    from extract_gpu_specs_groq import extract_gpu_specs
    from extract_motherboard_specs_groq import extract_motherboard_specs
    from extract_psu_specs_groq import extract_psu_specs
    from extract_cooler_specs_groq import extract_cooler_specs
    from extract_cabinet_specs_groq import extract_cabinet_specs
    from populate_ram_specs_from_extractions import populate_ram_specs
    from populate_ssd_specs_from_extractions import populate_ssd_specs

    llm_runners = [
        ("CPU", extract_cpu_specs),
        ("Monitor", extract_monitor_specs),
        ("GPU", extract_gpu_specs),
        ("Motherboard", extract_motherboard_specs),
        ("Power Supply", extract_psu_specs),
        ("CPU Cooler", extract_cooler_specs),
        ("Cabinet", extract_cabinet_specs),
    ]
    for label, fn in llm_runners:
        try:
            fn(limit=limit_per_category)
        except Exception as e:
            print(f"[Spec Extraction] {label} failed: {e}")

    for label, fn in (("RAM", populate_ram_specs), ("Storage", populate_ssd_specs)):
        try:
            fn()
        except Exception as e:
            print(f"[Spec Extraction] {label} failed: {e}")

    # Cabinet clearances come from retailer product pages, not titles. Runs after the
    # title-based cabinet pass so any clearance a title states explicitly is already in.
    try:
        from scrape_cabinet_clearance import fill_cabinet_clearance
        fill_cabinet_clearance(limit=limit_per_category)
    except Exception as e:
        print(f"[Spec Extraction] Cabinet clearance failed: {e}")

    # Air-cooler heights, likewise from product pages - what the cooler clearance rule reads.
    try:
        from scrape_cooler_height import fill_cooler_height
        fill_cooler_height(limit=limit_per_category)
    except Exception as e:
        print(f"[Spec Extraction] Cooler height failed: {e}")

    # Cabinet radiator support, for the AIO radiator-fit rule.
    try:
        from scrape_cabinet_radiators import fill_cabinet_radiators
        fill_cabinet_radiators(limit=limit_per_category)
    except Exception as e:
        print(f"[Spec Extraction] Cabinet radiators failed: {e}")


def execute_catalog_policy():
    """Re-apply the supported-platform policy and the catalog data-quality fixes.

    Without this the cleanup decays: every scrape can introduce a pre-10th-gen CPU, a
    DDR3 kit, an external USB drive or a cabinet whose form factor reads "Mid Tower",
    and each would be offered in the builder until someone re-ran these by hand. Both
    scripts are idempotent and make no API calls, so running them every cycle is cheap.

    Runs last because it reads the spec fields the two stages above populate.
    """
    scripts_path = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    from classify_legacy_products import classify
    from fix_catalog_data_quality import main as fix_data_quality
    from build_brand_registry import main as build_brand_registry

    try:
        classify(dry_run=False)
    except Exception as e:
        print(f"[Catalog Policy] legacy classification failed: {e}")

    try:
        fix_data_quality(dry_run=False)
    except Exception as e:
        print(f"[Catalog Policy] data-quality fixes failed: {e}")

    # Refresh the brand hints Stage 1 reads. Rebuilt after extraction, not before, so
    # every brand named confidently this cycle becomes a hint on the terse listings of
    # the same make next cycle - recognition of India-market brands improves instead of
    # staying flat. One grouped query, no API calls.
    try:
        build_brand_registry(apply=True)
    except Exception as e:
        print(f"[Catalog Policy] brand registry rebuild failed: {e}")


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


def execute_canonical_extraction_checked(limit_per_category: int = 10):
    """Runs execute_canonical_extraction, then fails loudly if it made no progress on a
    non-empty backlog (OPS-06). Snapshot and re-read use separate sessions so the check
    survives rows deleted mid-run."""
    with SessionLocal() as session:
        before = backlog_snapshot(session)

    execute_canonical_extraction(limit_per_category=limit_per_category)

    with SessionLocal() as session:
        after = state_of(session, before.keys())

    progress = count_extraction_progress(before, after)
    print(f"[Canonical Extraction] backlog_before={len(before)} progress={progress}")
    check_extraction_progress(len(before), progress)


PRICE_MAX_AGE = timedelta(hours=24)


def price_data_is_stale(latest: datetime | None, now: datetime, max_age: timedelta = PRICE_MAX_AGE) -> bool:
    """True when no price has been saved within max_age (or ever)."""
    return latest is None or now - latest > max_age


def stale_stores(
    latest_by_store: dict[str, datetime | None],
    now: datetime,
    max_age: timedelta = PRICE_MAX_AGE,
) -> list[str]:
    """Names (sorted) of stores whose latest saved price is stale or missing.

    Reuses price_data_is_stale per store, making `now` tz-consistent with each value
    exactly as check_price_freshness does, so a naive `now` compared against a tz-aware
    `latest` (or vice versa) never raises TypeError.
    """
    stale = []
    for name, latest in latest_by_store.items():
        this_now = now.replace(tzinfo=latest.tzinfo) if latest is not None and latest.tzinfo else now
        if price_data_is_stale(latest, this_now, max_age):
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

    now = datetime.now()
    stale_names = set(stale_stores(latest_by_store, now))
    if stale_names:
        stale_pairs = [(name, latest_by_store[name]) for name in sorted(stale_names)]
        raise RuntimeError(format_stale_message(stale_pairs))
    for name, latest in latest_by_store.items():
        print(f"[Freshness] {name}: latest price saved at {latest}")


# Airflow DAG Definition (evaluated when apache-airflow is installed)
try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    default_args = {
        "owner": "pc_builder",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
    }

    dag = DAG(
        "pc_builder_scheduled_scraper",
        default_args=default_args,
        description="Orchestrates periodic multi-store scraping for due targets",
        schedule="*/15 * * * *",
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        catchup=False,
    )

    process_targets_task = PythonOperator(
        task_id="process_due_targets",
        python_callable=execute_due_scrape_targets,
        dag=dag,
    )

    # all_done: extraction works through the backlog whether or not this cycle's scrape
    # succeeded, so a failed scrape (which now fails its task) must not stall it.
    canonical_extraction_task = PythonOperator(
        task_id="extract_canonical_identities",
        python_callable=execute_canonical_extraction_checked,
        trigger_rule="all_done",
        dag=dag,
    )

    # all_done: extraction now fails loudly when providers are exhausted (OPS-06), but the
    # spec and policy stages should still run on whatever is already keyed rather than
    # stalling the whole cycle on that failure.
    physical_specs_task = PythonOperator(
        task_id="extract_physical_specs",
        python_callable=execute_physical_spec_extraction,
        trigger_rule="all_done",
        dag=dag,
    )

    catalog_policy_task = PythonOperator(
        task_id="apply_catalog_policy",
        python_callable=execute_catalog_policy,
        dag=dag,
    )

    freshness_task = PythonOperator(
        task_id="check_price_freshness",
        python_callable=check_price_freshness,
        retries=0,
        trigger_rule="all_done",
        dag=dag,
    )

    # Strictly ordered: identities key the spec tables, and the policy reads the spec
    # fields, so each stage depends on the one before it.
    process_targets_task >> canonical_extraction_task >> physical_specs_task >> catalog_policy_task
    process_targets_task >> freshness_task
except ImportError:
    pass
