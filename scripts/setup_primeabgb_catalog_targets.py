"""
Script to clear old PrimeABGB (sid=4) product data and keyword targets,
and seed the 10 Category Catalog targets for PrimeABGB.
"""
from datetime import datetime, timezone
from sqlalchemy import text, select, delete
from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from common.enums.schedule_type import ScheduleType
from common.enums.target_type import TargetType


PRIMEABGB_CATALOG_TARGETS = [
    ("buy-online-price-india/cpu-processor/?per_page=48&filters=_stock_status[instock]", "CPU"),
    ("buy-online-price-india/motherboards/?per_page=48&filters=_stock_status[instock]", "Motherboard"),
    ("buy-online-price-india/graphic-cards-gpu/?per_page=48&filters=_stock_status[instock]", "GPU"),
    ("buy-online-price-india/ram-memory/?per_page=48&filters=_stock_status[instock]", "RAM"),
    ("buy-online-price-india/internal-hard-drive/?per_page=48&filters=_stock_status[instock]", "HDD"),
    ("buy-online-price-india/ssd/?per_page=48&filters=_stock_status[instock]", "SSD"),
    ("buy-online-price-india/led-monitors/?per_page=48&filters=_stock_status[instock]", "Monitor"),
    ("buy-online-price-india/power-supplies-smps/?per_page=48&filters=_stock_status[instock]", "PSU"),
    ("buy-online-price-india/gaming-headset/?per_page=48&filters=_stock_status[instock]", "Gaming Headset"),
    ("buy-online-price-india/gaming-wireless-routers/?per_page=48&filters=_stock_status[instock]", "Wireless Router"),
]


def setup_primeabgb():
    with SessionLocal() as session:
        store = session.scalar(select(Store).where(Store.name == "primeabgb"))
        if not store:
            print("[Error] Store primeabgb not found.")
            return

        sid = store.id
        print(f"Clearing old PrimeABGB product data and targets (store_id={sid})...")

        # Delete dependent spec tables for PrimeABGB
        spec_tables = [
            "cpu_specs", "gpu_specs", "motherboard_specs", "ram_specs",
            "ssd_specs", "psu_specs", "cabinet_specs", "cooler_specs", "monitor_specs"
        ]
        for tbl in spec_tables:
            session.execute(text(f"DELETE FROM {tbl} WHERE product_id IN (SELECT id FROM products WHERE sid = :sid)"), {"sid": sid})

        session.execute(text("DELETE FROM product_targets WHERE product_id IN (SELECT id FROM products WHERE sid = :sid)"), {"sid": sid})
        session.execute(text("DELETE FROM price_history WHERE product_id IN (SELECT id FROM products WHERE sid = :sid)"), {"sid": sid})
        session.execute(text("DELETE FROM products WHERE sid = :sid"), {"sid": sid})

        # Clear old keyword targets
        session.execute(delete(ScrapeTarget).where(ScrapeTarget.store_id == sid))

        # Seed new Category Catalog targets
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        added_count = 0

        for endpoint, category in PRIMEABGB_CATALOG_TARGETS:
            target = ScrapeTarget(
                store_id=sid,
                target_type=int(TargetType.CATEGORY),
                target_value=endpoint,
                schedule_type=int(ScheduleType.HOURLY),
                schedule_config={
                    "category": category,
                    "max_pages": 15,
                    "per_page": 48,
                },
                priority=1,
                enabled=True,
                next_scrape_at=now,
            )
            session.add(target)
            added_count += 1

        session.commit()
        print(f"Successfully cleared old PrimeABGB data and seeded {added_count} Category Catalog targets.")


if __name__ == "__main__":
    setup_primeabgb()
