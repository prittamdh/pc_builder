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

                try:
                    scraper = GenericScraper(client, store)
                    results = scraper.scrape_search_all_pages(
                        query=target.target_value,
                        max_pages=max_pages,
                    )

                    if results:
                        search_service.save_many(results)
                        print(f"[Scheduled Scraper] Saved {len(results)} products for '{target.target_value}'")

                    target_service.mark_scraped(target)

                except Exception as e:
                    print(f"[Scheduled Scraper Error] Failed scraping target '{target.target_value}': {e}")


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
except ImportError:
    pass
