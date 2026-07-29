"""
Script to clear old Vedant Computers (sid=3) product data and keyword targets,
and seed the 10 Category Catalog targets for Vedant Computers.
"""
from datetime import datetime, timezone
from sqlalchemy import text, select, delete
from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from common.enums.schedule_type import ScheduleType
from common.enums.target_type import TargetType


VEDANT_CATALOG_TARGETS = [
    ("pc-components/processor?limit=100", "CPU"),
    ("pc-components/motherboard?limit=100", "Motherboard"),
    ("pc-components/memory?limit=100", "RAM"),
    ("pc-components/gpu?limit=100", "GPU"),
    ("pc-components/smps?limit=100", "PSU"),
    ("pc-components/storage/solid-state-drive?limit=100", "SSD"),
    ("pc-components/storage/hard-disk-drive?limit=100", "HDD"),
    ("pc-components/cpu-cooler?limit=100", "CPU Cooler"),
    ("pc-components/cabinet?limit=100", "Cabinet"),
    ("pc-peripherals/output-devices/monitor?limit=100", "Monitor"),
]


def setup_vedant():
    with SessionLocal() as session:
        store = session.scalar(select(Store).where(Store.name == "vedant"))
        if not store:
            print("[Error] Store vedant not found.")
            return

        sid = store.id
        print(f"Clearing old Vedant Computers product data and targets (store_id={sid})...")

        # Delete dependent spec tables for Vedant Computers
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

        for endpoint, category in VEDANT_CATALOG_TARGETS:
            target = ScrapeTarget(
                store_id=sid,
                target_type=int(TargetType.CATEGORY),
                target_value=endpoint,
                schedule_type=int(ScheduleType.HOURLY),
                schedule_config={
                    "category": category,
                    "max_pages": 15,
                    "limit": 100,
                },
                priority=1,
                enabled=True,
                next_scrape_at=now,
            )
            session.add(target)
            added_count += 1

        session.commit()
        print(f"Successfully cleared old Vedant Computers data and seeded {added_count} Category Catalog targets.")


if __name__ == "__main__":
    setup_vedant()
