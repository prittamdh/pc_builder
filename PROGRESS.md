# PC Builder 2 - Progress Tracker

## Overall Phase Status

| Phase | Status | Notes |
| :--- | :---: | :--- |
| **Project Setup** | ✅ | Environment, dependencies, pyproject.toml configured |
| **Database Schema** | ✅ | PostgreSQL tables (`stores`, `products`, `price_history`, `scrape_targets`, 9 spec tables) |
| **Dual-Category Architecture (`category` & `p_category`)** | ✅ | `category` preserves raw store metadata while `p_category` powers production UI & PC Builder |
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
| **100% In-Stock Purge & Guard** | ✅ | Prevents new out-of-stock seeding while tracking out-of-stock history for existing items |

---

## Detailed Task Breakdown

### Database Infrastructure & `(sid, pid)` Architecture (Fully Live & Verified ✅)
- [x] **Composite Product Identity**: Implemented composite primary/unique key `(sid, pid)` across `products` and `price_history`.
- [x] **Dual Category Schema**: Added `p_category` column to `products` table and created Alembic migration `94ff4e0a9e14`.
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
- [x] **100% In-Stock Guard**: Prevents seeding stale out-of-stock items while preserving price history updates for active catalog items.
- [x] **Production `p_category` Normalization**: Categorized all 11,048 products into 10 canonical production categories (`Processor`, `Motherboard`, `Graphics Card`, `RAM`, `Storage`, `Cabinet`, `Power Supply`, `CPU Cooler`, `Monitor`, `Accessories`).
