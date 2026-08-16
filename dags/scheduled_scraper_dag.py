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

        with HttpClient() as client:
            for target in due_targets:
                store = store_service.get(target.store_id)
                if not store or not store.active:
                    continue

                print(f"[Scheduled Scraper] Scraping target '{target.target_value}' on {store.display_name}")

                target_val = str(target.target_value)
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
                    print(f"[Scheduled Scraper Error] Failed scraping target '{target_val}': {e}")


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

    canonical_extraction_task = PythonOperator(
        task_id="extract_canonical_identities",
        python_callable=execute_canonical_extraction,
        dag=dag,
    )

    process_targets_task >> canonical_extraction_task
except ImportError:
    pass
