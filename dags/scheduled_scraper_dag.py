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
from configs import settings
from pipeline.job_queue import reap
from pipeline.scrape_planning import enqueue_due_targets
# The stages and checks live in src/pipeline so the worker (plan 02-03) can run them too.
from pipeline.checks import check_price_freshness  # noqa: F401  (wired below)
from pipeline.tasks import (  # noqa: F401  (wired below)
    execute_canonical_extraction_checked,
    execute_catalog_policy,
    execute_physical_spec_extraction,
)


def queue_due_targets_for_agents():
    """Agent mode (SCRAPE_VIA_AGENTS): return expired leases to the queue, then queue
    page 1 of every due target. The extensions fetch; the API saves each upload."""
    with SessionLocal() as session:
        reaped = reap(session)
        queued = enqueue_due_targets(session)
    print(f"[Scheduled Scraper] agent mode: queued {queued} targets; "
          f"requeued {reaped['requeued']} expired leases, failed {reaped['failed']}")


def execute_due_scrape_targets(limit: int = 10, max_pages: int = 2):
    """Polls and executes due scrape targets across active stores."""
    if settings.SCRAPE_VIA_AGENTS:
        return queue_due_targets_for_agents()
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


def pipeline_failed_guard():
    """Raise so the DagRun's overall state is `failed` whenever any stage upstream
    failed this cycle.

    Every stage below this one runs with trigger_rule="all_done" so a failed stage
    (scraping, extraction, freshness) doesn't stop the stages after it from doing
    whatever work they still can - but that meant the run's *last* tasks (all
    similarly all_done/skip-tolerant) could still succeed, marking the whole run green
    even though a stage failed loudly. Wired downstream of every stage with
    trigger_rule="one_failed", this task only runs (and always raises) when at least
    one upstream task failed; it is skipped, and raises nothing, when everything
    upstream succeeded.
    """
    raise RuntimeError(
        "Pipeline failed: at least one upstream stage failed this cycle - see the "
        "failed task's log above."
    )


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

    # one_failed: every stage above tolerates a failed predecessor and keeps working
    # (all_done), so nothing upstream of this task stops the run - but that also meant
    # the run itself could finish green with a stage having failed loudly. This task
    # runs only when at least one upstream task failed, and always raises, so the
    # DagRun's own state reflects that.
    pipeline_failed_guard_task = PythonOperator(
        task_id="pipeline_failed_guard",
        python_callable=pipeline_failed_guard,
        retries=0,
        trigger_rule="one_failed",
        dag=dag,
    )

    # Strictly ordered: identities key the spec tables, and the policy reads the spec
    # fields, so each stage depends on the one before it.
    process_targets_task >> canonical_extraction_task >> physical_specs_task >> catalog_policy_task
    process_targets_task >> freshness_task

    [
        process_targets_task,
        canonical_extraction_task,
        physical_specs_task,
        catalog_policy_task,
        freshness_task,
    ] >> pipeline_failed_guard_task
except ImportError:
    pass
