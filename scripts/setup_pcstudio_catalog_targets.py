"""
Script to clear old PCStudio (sid=2) product data and keyword targets,
and seed the 9 Category Catalog targets for PCStudio.
"""
from datetime import datetime, timezone
from sqlalchemy import text, select, delete
from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from common.enums.schedule_type import ScheduleType
from common.enums.target_type import TargetType


PCSTUDIO_CATALOG_TARGETS = [
    ("product-category/processor/?products-per-page=all", "CPU"),
    ("product-category/motherboard/?products-per-page=all", "Motherboard"),
    ("product-category/ram/?products-per-page=all", "RAM"),
    ("product-category/storage/?products-per-page=all", "SSD"),
    ("product-category/cabinets/?products-per-page=all", "Cabinet"),
    ("product-category/cpu-cooler/?products-per-page=all", "CPU Cooler"),
    ("product-category/graphics-card/?products-per-page=all", "GPU"),
    ("product-category/power-supply/?products-per-page=all", "PSU"),
    ("product-category/monitor/?products-per-page=all", "Monitor"),
]


def setup_pcstudio():
    with SessionLocal() as session:
        store = session.scalar(select(Store).where(Store.name == "pcstudio"))
        if not store:
            print("[Error] Store pcstudio not found.")
            return

        sid = store.id
        print(f"Clearing old PCStudio product data and targets (store_id={sid})...")

        # Delete dependent spec tables for PCStudio
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

        for endpoint, category in PCSTUDIO_CATALOG_TARGETS:
            target = ScrapeTarget(
                store_id=sid,
                target_type=int(TargetType.CATEGORY),
                target_value=endpoint,
                schedule_type=int(ScheduleType.HOURLY),
                schedule_config={
                    "category": category,
                    "max_pages": 15,
                },
                priority=1,
                enabled=True,
                next_scrape_at=now,
            )
            session.add(target)
            added_count += 1

        session.commit()
        print(f"Successfully cleared old PCStudio data and seeded {added_count} Category Catalog targets.")


if __name__ == "__main__":
    setup_pcstudio()
