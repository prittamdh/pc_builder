# PC Builder 2 - Progress Tracker

## Overall Phase Status

| Phase | Status | Notes |
| :--- | :---: | :--- |
| **Project Setup** | ✅ | Environment, dependencies, pyproject.toml configured |
| **Database Schema** | ✅ | PostgreSQL tables (`stores`, `products`, `price_history`, `scrape_targets`, 9 spec tables) |
| **Generic Search Scraper** | ✅ | Selector-based, Shopify API, FleetCart API, HTMX, and Next.js App Router scraping |
| **Search Pipeline (Product + PriceHistory)** | ✅ | Automatically persists scraped search items & price snapshots (100% in-stock filtering) |
| **Multi-Store Scraping** | ✅ | 10 stores seeded & verified (`mdcomputers`, `pcstudio`, `vedant`, `primeabgb`, `elitehubs`, `clarion`, `computechstore`, `tpstech`, `modxcomputers`, `tlggaming`) |
| **Product Page Scraper** | ✅ | JSON-LD & fallback extraction for detailed product pages |
| **sid/pid Refactor** | ✅ | Completely implemented & verified end-to-end |
| **Pagination & Scrape Target Management** | ✅ | Multi-page pagination, target seeding & target execution verified |
| **Airflow Scheduling & Web UI** | ✅ | Airflow 2.9.1 container running live on `http://localhost:8085` |
| **FastAPI Backend** | ✅ | Production-grade REST API server & endpoints (`src/api/`) live on `http://127.0.0.1:8000` |
| **Frontend UI** | ✅ | Glassmorphic dark mode UI live on `http://localhost:8000/` |
| **PC Builder Assembly Tool** | ✅ | Component slots, socket/RAM/TDP compatibility & multi-store optimizer |
| **100% In-Stock Purge & Guard** | ✅ | Eliminated 6,677 out-of-stock items, strictly enforcing in-stock integrity |
| **Granular Category Enforcement** | ✅ | 100% granular categories enforced across all 11,024 active products |

---

## Detailed Task Breakdown

### Database Infrastructure & `(sid, pid)` Architecture (Fully Live & Verified ✅)
- [x] **Composite Product Identity**: Implemented composite primary/unique key `(sid, pid)` across `products` and `price_history`.
- [x] **Store Management**: Configurable store schema (`stores`) with dynamic CSS selectors, pagination templates, and active flags.
- [x] **Alembic Migrations**: Schema migrations with version isolation (`app_alembic_version`) to avoid Airflow metadata table conflicts.
- [x] **Component Specification Tables**: 9 normalized specification tables (`cpu_specs`, `gpu_specs`, `motherboard_specs`, `ram_specs`, `ssd_specs`, `psu_specs`, `cabinet_specs`, `cooler_specs`, `monitor_specs`).

### Multi-Store Scraping Engine (10 Major Indian PC Hardware Retailers Live & Verified ✅)
- [x] **MDComputers (`sid = 1`)**: Magento HTML catalog scraping (1,460 in-stock products).
- [x] **PCStudio (`sid = 2`)**: WooCommerce catalog scraping (1,839 in-stock products).
- [x] **Vedant Computers (`sid = 3`)**: OpenCart catalog scraping (588 in-stock products).
- [x] **PrimeABGB (`sid = 4`)**: WooCommerce catalog scraping (841 in-stock products).
- [x] **EliteHubs (`sid = 6`)**: Shopify JSON API multi-page pagination (1,650 in-stock products).
- [x] **Clarion Computers (`sid = 7`)**: FleetCart PWA JSON API multi-page pagination (405 in-stock products).
- [x] **Computech Store (`sid = 8`)**: WooCommerce HTMX multi-page pagination (1,941 in-stock products).
- [x] **TPS Tech (`sid = 9`)**: Shopify JSON API multi-page pagination (1,661 in-stock products).
- [x] **ModxComputers (`sid = 10`)**: Next.js App Router payload extraction with `in_stock=true` (491 in-stock products).
- [x] **TLG Gaming (`sid = 11`)**: OpenCart Journal 3 theme with `fq=1` in-stock filter (148 in-stock products).

### Data Integrity & Granular Classification (Fully Live & Verified ✅)
- [x] **100% In-Stock Enforcement**: Purged 6,677 out-of-stock rows and added real-time in-stock filter guard in `SearchService.save()`.
- [x] **Granular Category Classification**: Mapped target-level categories onto `products.category`, eliminating all generic `"Accessories"`, `"CPU"`, and `"GPU"` umbrella clubbing across 11,024 active products.

### FastAPI REST Backend & PC Builder Engine (Fully Live & Verified ✅)
- [x] **REST Endpoints**: `/api/v1/stores`, `/api/v1/products`, `/api/v1/products/{id}`, `/api/v1/products/{id}/history`.
- [x] **PC Builder Compatibility Engine**: Socket matching (AM5, LGA1700, LGA1851), RAM generation (DDR4, DDR5), TDP wattage estimation, and multi-store cost optimization.
- [x] **Static Mounting & CORS**: Mounting glassmorphic dark-mode web application directly at `http://127.0.0.1:8000/`.
