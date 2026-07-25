# PC Builder 2 - Progress Tracker

## Overall Phase Status

| Phase | Status | Notes |
| :--- | :---: | :--- |
| **Project Setup** | ✅ | Environment, dependencies, pyproject.toml configured |
| **Database Schema** | ✅ | PostgreSQL tables (`stores`, `products`, `price_history`, `scrape_targets`) via Alembic |
| **Generic Search Scraper** | ✅ | Selector-based scraping for all configured stores |
| **Search Pipeline (Product + PriceHistory)** | ✅ | Automatically persists scraped search items & price snapshots |
| **Multi-Store Scraping** | ✅ | 4 stores seeded & verified (`mdcomputers`, `pcstudio`, `vedant`, `primeabgb`) |
| **Product Page Scraper** | ✅ | JSON-LD & fallback extraction for detailed product pages |
| **sid/pid Refactor** | ✅ | Completely implemented & verified end-to-end |
| **Pagination & Scrape Target Management** | ✅ | Multi-page pagination, target seeding & target execution verified |
| **Airflow Container Verification** | 🚧 | Docker compose created (`docker-compose.yml`); pending container spin-up & DAG validation |
| **FastAPI Backend** | ⏳ | REST API for products, price history, and search |
| **Frontend UI** | ⏳ | Web interface for price comparison and build planning |
| **PC Builder Assembly Tool** | ⏳ | Compatibility checker & budget build calculator |
| **Advanced Features** | ⏳ | Price drop alerts, wishlist, stock notifications |

---

## Detailed Task Breakdown

### Airflow Docker Container Verification (In Progress 🚧)

- [x] **Docker Check**: Confirmed Docker version 29.5.3 installed on machine.
- [x] **Airflow Docker Compose**: Created `docker-compose.yml` with Airflow 2.9.1 + PostgreSQL.
- [x] **DAG Code**: Created `dags/scheduled_scraper_dag.py`.
- [ ] **Container Launch**: Execute `docker compose up -d` to launch Airflow webserver & scheduler.
- [ ] **DAG Validation**: Verify DAG parses without import errors and executes scheduled tasks in Airflow UI.
