"""
Script to remove old keyword targets for MDComputers (store_id=1)
and seed the 16 exact Category Catalog URLs with hard category mapping and max_pages=15.
"""
from datetime import datetime, timezone
from sqlalchemy import select, delete
from db.session import SessionLocal
from db.models.scrape_target import ScrapeTarget
from db.models.store import Store
from common.enums.schedule_type import ScheduleType
from common.enums.target_type import TargetType


MDCOMPUTERS_CATALOG_TARGETS = [
    ("catalog/processor", "CPU"),
    ("catalog/cpu-cooler", "CPU Cooler"),
    ("catalog/motherboard", "Motherboard"),
    ("catalog/graphics-card", "GPU"),
    ("catalog/desktop-ram", "Desktop RAM"),
    ("catalog/laptop-ram", "Laptop RAM"),
    ("catalog/internal-hdd", "Internal HDD"),
    ("catalog/external-hdd", "External HDD"),
    ("catalog/sata-ssd", "SATA SSD"),
    ("catalog/gen3-ssd", "Gen3 NVMe SSD"),
    ("catalog/gen4-ssd", "Gen4 NVMe SSD"),
    ("catalog/gen5-ssd", "Gen5 NVMe SSD"),
    ("catalog/external-ssd", "External SSD"),
    ("catalog/monitor", "Monitor"),
    ("catalog/cabinet", "Cabinet"),
    ("catalog/smps", "PSU"),
]


def seed_mdcomputers_targets():
    with SessionLocal() as session:
        store = session.scalar(select(Store).where(Store.name == "mdcomputers"))
        if not store:
            print("[Error] MDComputers store configuration not found.")
            return

        print(f"Cleaning existing scrape targets for MDComputers (store_id={store.id})...")
        session.execute(delete(ScrapeTarget).where(ScrapeTarget.store_id == store.id))
        session.commit()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        added_count = 0

        for endpoint, category in MDCOMPUTERS_CATALOG_TARGETS:
            target = ScrapeTarget(
                store_id=store.id,
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
        print(f"Successfully seeded {added_count} Category Catalog targets for MDComputers with hard category filters.")


if __name__ == "__main__":
    seed_mdcomputers_targets()
