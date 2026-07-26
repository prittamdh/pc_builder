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
                        search_service.save_many(results, target_id=target.id)
                        print(f"[Scheduled Scraper] Saved {len(results)} products for '{target.target_value}' (target_id={target.id})")

                    target_service.mark_scraped(target)

                except Exception as e:
                    print(f"[Scheduled Scraper Error] Failed scraping target '{target.target_value}': {e}")


def execute_unscraped_product_enrichment(limit: int = 10):
    """Enriches static metadata for unique products missing details."""
    from services.product_service import ProductService

    with SessionLocal() as session:
        product_service = ProductService(session)
        store_service = StoreService(session)

        unscraped_products = product_service.get_unscraped_products(limit=limit)
        print(f"[Product Scraper] Found {len(unscraped_products)} unscraped products to enrich.")

        if not unscraped_products:
            return

        with HttpClient() as client:
            for db_product in unscraped_products:
                store = store_service.get(db_product.sid)
                if not store or not store.active:
                    continue

                try:
                    scraper = GenericScraper(client, store)
                    p_details = scraper.scrape_product(db_product.product_url)
                    if p_details:
                        product_service.save(p_details)
                        print(f"[Product Scraper] Enriched static metadata for '{db_product.name}'")
                except Exception as e:
                    print(f"[Product Scraper Error] Failed '{db_product.name}': {e}")


def execute_catalog_normalization(limit: int = 50):
    """Normalizes specifications and populates category tables for scraped products."""
    from services.normalization_service import NormalizationService

    with SessionLocal() as session:
        service = NormalizationService(session)
        count = service.normalize_all_unclassified(limit=limit)
        print(f"[Normalizer Task] Normalized and populated category specs for {count} products.")


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

    enrich_products_task = PythonOperator(
        task_id="enrich_unscraped_products",
        python_callable=execute_unscraped_product_enrichment,
        dag=dag,
    )

    normalize_catalog_task = PythonOperator(
        task_id="normalize_catalog_specs",
        python_callable=execute_catalog_normalization,
        dag=dag,
    )

    process_targets_task >> enrich_products_task >> normalize_catalog_task
except ImportError:
    pass
