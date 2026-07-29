"""
Setup script to initialize Clarion Computers (store_id=7) and Computech Store (store_id=8),
clear any previous data, and seed Granular Category Catalog Targets for both stores.
"""
from datetime import datetime, timezone
from sqlalchemy import text, select, delete
from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from common.enums.schedule_type import ScheduleType
from common.enums.target_type import TargetType


CLARION_TARGETS = [
    ("product-category/desktop-processors", "Desktop Processors"),
    ("product-category/motherboards", "Motherboards"),
    ("product-category/desktop-ram", "Desktop RAM"),
    ("product-category/graphics-card", "Graphics Card"),
    ("product-category/ssd", "SSD"),
    ("product-category/power-supply", "Power Supply"),
    ("product-category/internal-hard-drive", "Internal Hard Drive"),
    ("product-category/cabinet", "Cabinet"),
    ("product-category/cooling-systems", "Cooling Systems"),
]


COMPUTECH_TARGETS = [
    ("product-category/processor/", "Processor"),
    ("product-category/motherboard/", "Motherboard"),
    ("product-category/storage/hard-disk/?sort=newest&storage-type=HDD", "Internal HDD"),
    ("product-category/storage/hard-disk/?sort=newest&storage-type=External%20HDD", "External HDD"),
    ("product-category/memory-ram/?sort=newest&memory-type=Desktop%20Memory", "Desktop RAM"),
    ("product-category/memory-ram/?sort=newest&memory-type=Laptop%20Memory", "Laptop RAM"),
    ("product-category/graphics-card/", "Graphics Card"),
    ("product-category/storage/ssd/?sort=newest&storage-type=INTERNAL%20SSD", "Internal SSD"),
    ("product-category/storage/ssd/?sort=newest&storage-type=External%20SSD", "External SSD"),
    ("product-category/cooling-system/", "Cooling System"),
    ("product-category/power-supply/", "Power Supply"),
    ("product-category/cabinet-case/", "Cabinet Case"),
]


def setup_stores():
    with SessionLocal() as session:
        print("Setting up Clarion Computers and Computech Store in PostgreSQL...")

        # 1. Clarion Computers
        clarion = session.scalar(select(Store).where(Store.name == "clarion"))
        if not clarion:
            clarion = Store(
                name="clarion",
                display_name="Clarion Computers",
                domain="shop.clarioncomputers.in",
                base_url="https://shop.clarioncomputers.in",
                search_endpoint="https://shop.clarioncomputers.in/products?category={query}",
                search_config={
                    "platform": "fleetcart",
                    "page_endpoint": "https://shop.clarioncomputers.in/products?category={query}&page={page}",
                },
                product_config={
                    "platform": "fleetcart",
                },
            )
            session.add(clarion)
            session.flush()

        # 2. Computech Store
        computech = session.scalar(select(Store).where(Store.name == "computechstore"))
        if not computech:
            computech = Store(
                name="computechstore",
                display_name="Computech Store",
                domain="computechstore.in",
                base_url="https://computechstore.in",
                search_endpoint="https://computechstore.in/?s={query}&post_type=product",
                search_config={
                    "platform": "woocommerce",
                    "page_endpoint": "https://computechstore.in/product-category/{query}/?paged={page}",
                    "selectors": {
                        "product_card": "div.product, div[class*='product']",
                        "title": "a[href*='/product/']",
                        "price": ".price",
                        "mrp": "del",
                        "image": "img",
                    },
                    "attributes": {
                        "url": "href",
                        "image": "src",
                    },
                },
                product_config={},
            )
            session.add(computech)
            session.flush()

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for store, target_list in [(clarion, CLARION_TARGETS), (computech, COMPUTECH_TARGETS)]:
            sid = store.id
            print(f"Clearing old target/product data for '{store.name}' (sid={sid})...")

            session.execute(text("DELETE FROM product_targets WHERE product_id IN (SELECT id FROM products WHERE sid = :sid)"), {"sid": sid})
            session.execute(text("DELETE FROM price_history WHERE product_id IN (SELECT id FROM products WHERE sid = :sid)"), {"sid": sid})
            session.execute(text("DELETE FROM products WHERE sid = :sid"), {"sid": sid})
            session.execute(delete(ScrapeTarget).where(ScrapeTarget.store_id == sid))

            for endpoint, category in target_list:
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

        session.commit()
        print("=" * 80)
        print("CLARION & COMPUTECH STORE INITIALIZED SUCCESSFULLY IN POSTGRESQL!")


if __name__ == "__main__":
    setup_stores()
