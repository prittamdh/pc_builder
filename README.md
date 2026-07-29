# PC Builder 2 - Multi-Store PC Component Price Tracker & Assembly Compatibility Engine

A production-grade, multi-store PC component price aggregator, real-time spec normalizer, and PC assembly compatibility optimization engine built for Indian PC hardware retailers.

---

## 🌟 Key Features

1. **Multi-Engine Web Scraper**:
   - Supports HTML Selector Scraping (WooCommerce, Magento, OpenCart Journal 3).
   - Supports Shopify JSON API (`products.json?limit=250`).
   - Supports FleetCart PWA JSON API (`/products?category={slug}`).
   - Supports WooCommerce HTMX Pagination (`HX-Request: true`).
   - Supports Next.js App Router Payload Extraction (`in_stock=true`).
2. **10 Major Indian PC Hardware Retailers Integrated**:
   - **MDComputers** (`mdcomputers.in`)
   - **PCStudio** (`pcstudio.in`)
   - **Vedant Computers** (`vedantcomputers.com`)
   - **PrimeABGB** (`primeabgb.com`)
   - **EliteHubs** (`elitehubs.com`)
   - **Clarion Computers** (`shop.clarioncomputers.in`)
   - **Computech Store** (`computechstore.in`)
   - **TPS Tech** (`tpstech.in`)
   - **ModxComputers** (`modxcomputers.com`)
   - **TLG Gaming** (`tlggaming.com`)
3. **100% In-Stock Data Integrity**:
   - Automatically purges out-of-stock items and guards PostgreSQL against out-of-stock data insertion.
4. **Granular Classification & Spec Normalization**:
   - Zero umbrella clubbing: 100% granular categories (`AMD Processor`, `Intel Processor`, `M.2 NVMe SSD`, `Desktop RAM (DDR5)`, `Cabinet`, `Power Supply`, `NVIDIA RTX 50 Series`, etc.).
   - Normalizes hardware specifications into 9 dedicated relational spec tables (`cpu_specs`, `gpu_specs`, `motherboard_specs`, `ram_specs`, `ssd_specs`, `psu_specs`, `cabinet_specs`, `cooler_specs`, `monitor_specs`).
5. **PC Builder Assembly Tool**:
   - Automated hardware compatibility checks (Socket AM5 / LGA1700 / LGA1851, RAM DDR4/DDR5, TDP Wattage estimation).
   - Multi-store cost optimization across all 10 retailers.
6. **Airflow 2.9.1 & FastAPI Web Dashboard**:
   - Background DAG target execution every 15 minutes.
   - Glassmorphic dark-mode web application and REST API endpoints.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic
- **Database**: PostgreSQL 15 (Docker container)
- **Scraper / HTTP**: `curl_cffi` (HTTP/2 fingerprinting bypass), BeautifulSoup4, HTMX, Next.js JSON Parser
- **Orchestration**: Apache Airflow 2.9.1 (Docker container)
- **Frontend**: Glassmorphic Dark UI (Vanilla CSS + HTML5 + JavaScript)

---

## 🚀 Getting Started

### Prerequisites

- Docker Desktop & Docker Compose
- Python 3.12+

### Installation & Setup

1. **Clone repository**:
   ```bash
   git clone https://github.com/prittamdh/pc_builder2.git
   cd pc_builder2
   ```

2. **Launch PostgreSQL & Airflow containers**:
   ```bash
   docker compose up -d
   ```

3. **Install Python dependencies**:
   ```bash
   pip install -e .
   ```

4. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

5. **Run tests**:
   ```bash
   pytest
   ```

---

## 📊 Live Database Catalog Summary

- **Total In-Stock Products**: **11,024 Active Products**
- **Active Retailers**: **10 Stores**
- **Out-of-Stock Products**: **0 (100% In-Stock)**
