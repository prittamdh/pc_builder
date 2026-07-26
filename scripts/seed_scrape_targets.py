from datetime import datetime
from sqlalchemy.orm import Session

from common.enums.schedule_type import ScheduleType
from common.enums.target_type import TargetType
from db.models.scrape_target import ScrapeTarget
from db.models.store import Store
from db.session import engine


TARGET_KEYWORDS = [
    # CPUs
    "ryzen 9000",
    "ryzen 7000",
    "intel core ultra",
    "intel core i9",
    "intel core i7",
    "intel core i5",
    # GPUs
    "rtx 5090",
    "rtx 5080",
    "rtx 5070 ti",
    "rtx 5070",
    "rtx 5060 ti",
    "rtx 5060",
    "rx 9070 xt",
    "rx 9070",
    # Motherboards
    "b850 motherboard",
    "x870 motherboard",
    "b650 motherboard",
    "z890 motherboard",
    # Memory
    "ddr5 ram",
    "ddr4 ram",
    "32gb ddr5",
    "64gb ddr5",
    "6000mhz ram",
    # Storage
    "nvme ssd",
    "1tb ssd",
    "2tb ssd",
    "gen5 ssd",
    # Power Supplies
    "650w psu",
    "750w psu",
    "850w psu",
    "1000w psu",
    # Cooling
    "air cooler",
    "aio cooler",
    "240mm aio",
    "360mm aio",
    # Cases
    "atx cabinet",
    "matx cabinet",
    # Displays
    "1440p monitor",
    "4k monitor",
    "oled monitor",
]


def main():
    with Session(engine) as session:
        stores = session.query(Store).filter(Store.active == True).all()

        if not stores:
            print("No active stores found. Please run seed_stores.py first.")
            return

        added_count = 0
        now = datetime.utcnow()

        for store in stores:
            for keyword in TARGET_KEYWORDS:
                exists = (
                    session.query(ScrapeTarget)
                    .filter(
                        ScrapeTarget.store_id == store.id,
                        ScrapeTarget.target_type == int(TargetType.SEARCH),
                        ScrapeTarget.target_value == keyword,
                    )
                    .first()
                )

                if not exists:
                    target = ScrapeTarget(
                        store_id=store.id,
                        target_type=int(TargetType.SEARCH),
                        target_value=keyword,
                        schedule_type=int(ScheduleType.DAILY),
                        schedule_config={},
                        priority=1,
                        enabled=True,
                        next_scrape_at=now,
                    )
                    session.add(target)
                    added_count += 1

        session.commit()
        print(f"Seeded {added_count} new scrape targets for {len(stores)} active stores.")


if __name__ == "__main__":
    main()
