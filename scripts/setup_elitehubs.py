"""
Setup script to initialize EliteHubs store (sid=5),
clear any previous data, and seed 17 Granular Category Catalog Targets.
"""
from datetime import datetime, timezone
from sqlalchemy import text, select, delete
from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from common.enums.schedule_type import ScheduleType
from common.enums.target_type import TargetType


ELITEHUBS_CATALOG_TARGETS = [
    ("collections/processor", "Processor"),
    ("collections/motherboard", "Motherboard"),
    ("collections/pc-cabinet", "Cabinet"),
    ("collections/nvidia-graphic-cards", "Graphics Card (NVIDIA)"),
    ("collections/amd-graphic-cards", "Graphics Card (AMD)"),
    ("collections/pc-coolers", "CPU Cooler"),
    ("collections/power-supply-unit-psu", "Power Supply / SMPS"),
    ("collections/ddr4-ram", "Desktop RAM (DDR4)"),
    ("collections/ddr5-ram", "Desktop RAM (DDR5)"),
    ("collections/ddr4-laptop-ram", "Laptop RAM (DDR4)"),
    ("collections/ddr5-laptop-ram", "Laptop RAM (DDR5)"),
    ("collections/m-2-nvme-ssd", "M.2 NVMe SSD"),
    ("collections/gen4-ssd", "Gen4 NVMe SSD"),
    ("collections/gen5-ssd", "Gen5 NVMe SSD"),
    ("collections/laptop-ssd", "Laptop SSD"),
    ("collections/external-hard-disk", "External Hard Disk"),
    ("collections/monitor", "Monitor"),
]


def setup_elitehubs():
    with SessionLocal() as session:
        print("Initializing EliteHubs store in PostgreSQL...")

        store = session.scalar(select(Store).where(Store.name == "elitehubs"))
        if not store:
            store = Store(
                name="elitehubs",
                display_name="EliteHubs",
                domain="elitehubs.com",
                base_url="https://elitehubs.com",
                search_endpoint="https://elitehubs.com/search?q={query}",
                search_config={
                    "platform": "shopify",
                    "page_endpoint": "https://elitehubs.com/{query}/products.json?limit=250",
                },
                product_config={
                    "platform": "shopify",
                },
            )
            session.add(store)
            session.flush()

        sid = store.id
        print(f"Clearing old EliteHubs product data (store_id={sid})...")

        spec_tables = [
            "cpu_specs", "gpu_specs", "motherboard_specs", "ram_specs",
            "ssd_specs", "psu_specs", "cabinet_specs", "cooler_specs", "monitor_specs"
        ]
        for tbl in spec_tables:
            session.execute(text(f"DELETE FROM {tbl} WHERE product_id IN (SELECT id FROM products WHERE sid = :sid)"), {"sid": sid})

        session.execute(text("DELETE FROM product_targets WHERE product_id IN (SELECT id FROM products WHERE sid = :sid)"), {"sid": sid})
        session.execute(text("DELETE FROM price_history WHERE product_id IN (SELECT id FROM products WHERE sid = :sid)"), {"sid": sid})
        session.execute(text("DELETE FROM products WHERE sid = :sid"), {"sid": sid})
        session.execute(delete(ScrapeTarget).where(ScrapeTarget.store_id == sid))

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        added_count = 0

        for endpoint, category in ELITEHUBS_CATALOG_TARGETS:
            target = ScrapeTarget(
                store_id=sid,
                target_type=int(TargetType.CATEGORY),
                target_value=endpoint,
                schedule_type=int(ScheduleType.HOURLY),
                schedule_config={
                    "category": category,
                    "max_pages": 1,
                    "platform": "shopify",
                },
                priority=1,
                enabled=True,
                next_scrape_at=now,
            )
            session.add(target)
            added_count += 1

        session.commit()
        print(f"Successfully initialized EliteHubs (store_id={sid}) with {added_count} Granular Category Catalog targets.")


if __name__ == "__main__":
    setup_elitehubs()
