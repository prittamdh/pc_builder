# PROJECT_MAP.md

## Application Entry & Infrastructure
- **src/main.py**: Application entry point.
- **docker-compose.yml**: Docker Compose configuration running Airflow webserver/scheduler & PostgreSQL.

## Domain Models
- **src/domain/base.py**: Base scraper and parser interfaces.
- **src/domain/store.py**: Store domain model representing retailer settings.
- **src/domain/search_result.py**: Search result model containing store (`store`), store ID (`sid`), product ID (`pid`), price, MRP, and URLs.
- **src/domain/product.py**: Product details model containing `sid`, `pid`, metadata, specifications, and availability.

## Database Models & ORM
- **src/db/base.py**: SQLAlchemy DeclarativeBase initialization.
- **src/db/session.py**: Database engine and SessionLocal session factory.
- **src/db/models/mixins.py**: Base model mixins (`TimestampMixin` with `created_at` and `updated_at`).
- **src/db/models/store.py**: Store model storing configuration, CSS/attribute selectors, and search endpoints.
- **src/db/models/product.py**: Product model uniquely constrained on `(sid, pid)`.
- **src/db/models/price_history.py**: Historical price snapshots linked to `products`.
- **src/db/models/scrape_target.py**: Scheduled scraping target model for category/search URLs.

## Repositories
- **src/db/repositories/base_repository.py**: Base repository wrapping DB session operations.
- **src/db/repositories/store_repository.py**: Database operations for store configurations.
- **src/db/repositories/product_repository.py**: CRUD operations for products using composite key `(sid, pid)`.
- **src/db/repositories/price_history_repository.py**: Database operations for price history records.
- **src/db/repositories/scrape_target_repository.py**: Querying and updating scrape targets and schedules.

## Services
- **src/services/store_service.py**: Service to retrieve and manage store configurations.
- **src/services/search_service.py**: Service to persist search results and insert price history entries.
- **src/services/product_service.py**: Service to update detailed product metadata from product pages.
- **src/services/scrape_target_service.py**: Service to manage upcoming scraping targets and scheduling queue.

## Scrapers & Parsers
- **src/scrapers/http_client.py**: Resilient HTTP client wrapper for fetching store pages.
- **src/scrapers/base_scraper.py**: Abstract base scraper interface.
- **src/scrapers/base_parser.py**: Abstract base parser interface.
- **src/scrapers/generic_scraper.py**: Unified scraper handling search (single & multi-page pagination) and product scraping for all stores.
- **src/scrapers/generic_parser.py**: Unified parser extracting HTML elements/JSON-LD into domain models.

## Airflow DAGs
- **dags/scheduled_scraper_dag.py**: Airflow DAG `pc_builder_scheduled_scraper` orchestrating multi-store scraping for due targets every 15 minutes.

## Active Core Scripts
- **scripts/seed_stores.py**: Seeds supported stores (`mdcomputers`, `pcstudio`, `vedant`, `primeabgb`) and selectors/pagination endpoints into DB.
- **scripts/seed_scrape_targets.py**: Seeds initial search targets (`rtx 5070`, `rtx 5080`, `ryzen 9000`, `ddr5 ram`) for all active stores into `scrape_targets`.
- **scripts/test_connection.py**: Verifies PostgreSQL connection.
- **scripts/test_store_service.py**: Tests `StoreService` methods against active stores.
- **scripts/test_all_stores.py**: Scrapes search results for every active store and saves products/price history.
- **scripts/test_product_scraper.py**: Tests fetching and parsing detailed product pages.
- **scripts/test_pagination_and_targets.py**: Tests multi-page pagination scraping for due scrape targets.
- **scripts/test_airflow_task.py**: Verifies Airflow task execution callable outside Airflow environment.

## Deprecated / Obsolete Scripts
- **scripts/test_mdcomputers_scraper.py**: [DEPRECATED] Hardcoded single-store scraper (superseded by `test_all_stores.py`).
- **scripts/run_search.py**: [DEPRECATED] Legacy static HTML file parser.
- **scripts/setup_db.py**: [DEPRECATED] Empty script (superseded by Alembic migrations).