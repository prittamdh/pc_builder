"""
Setup script to initialize TPS Tech (store_id=9), ModxComputers (store_id=10), and TLG Gaming (store_id=11),
clear any previous data, and seed Granular Category Catalog Targets for all three stores.
"""
from datetime import datetime, timezone
from sqlalchemy import text, select, delete
from db.session import SessionLocal
from db.models.store import Store
from db.models.scrape_target import ScrapeTarget
from common.enums.schedule_type import ScheduleType
from common.enums.target_type import TargetType


TPSTECH_TARGETS = [
    ("collections/amd-processor", "AMD Processor"),
    ("collections/intel-desktop-processors", "Intel Processor"),
    ("collections/amd-ryzen-threadripper-processors", "Threadripper Processor"),
    ("collections/power-supply", "Power Supply"),
    ("collections/cpu-air-cooler", "CPU Air Cooler"),
    ("collections/cpu-liquid-cooler", "CPU Liquid Cooler"),
    ("collections/cabinets-all", "Cabinet"),
    ("collections/amd-motherboard", "AMD Motherboard"),
    ("collections/motherboard-intel-chipset", "Intel Motherboard"),
    ("collections/amd-radeon-graphics-cards", "AMD Graphics Card"),
    ("collections/nvidia-rtx-50-series-graphics-card", "NVIDIA RTX 50 Series"),
    ("collections/nvidia-rtx-30-series-graphics-card", "NVIDIA RTX 30 Series"),
    ("collections/nvme-ssds", "NVMe SSD"),
    ("collections/m-2-ssds", "M.2 SSD"),
    ("collections/ssd", "SSD"),
    ("collections/external-portable-ssds", "External Portable SSD"),
    ("collections/internal-hdd", "Internal HDD"),
    ("collections/external-portable-hdd", "External Portable HDD"),
    ("collections/monitor", "Monitor"),
    ("collections/laptop-memory", "Laptop RAM"),
    ("collections/desktop-memory", "Desktop RAM"),
]


MODX_TARGETS = [
    ("product-category/pc-components/processor/", "Processor"),
    ("product-category/pc-components/motherboard/", "Motherboard"),
    ("product-category/pc-components/cpu-cooler/", "CPU Cooler"),
    ("product-category/pc-components/ram/", "RAM"),
    ("product-category/pc-components/graphics-card/", "Graphics Card"),
    ("product-category/pc-components/internal-ssd/", "Internal SSD"),
    ("product-category/pc-components/hard-drive/", "Hard Drive"),
    ("product-category/pc-components/power-supply/", "Power Supply"),
    ("product-category/pc-components/cabinets/", "Cabinet"),
]


TLG_TARGETS = [
    ("processors?fq=1", "Processor"),
    ("motherboards?fq=1", "Motherboard"),
    ("memory-ram?fq=1", "RAM"),
    ("ssd?fq=1", "SSD"),
    ("graphic-cards?fq=1", "Graphics Card"),
    ("power-supply-smps?fq=1", "Power Supply"),
    ("cpu-cooler?fq=1", "CPU Cooler"),
    ("pc-cabinets?fq=1", "Cabinet"),
    ("monitors?fq=1", "Monitor"),
    ("hdd", "HDD"),
]


def setup_three_stores():
    with SessionLocal() as session:
        print("Setting up TPS Tech, ModxComputers, and TLG Gaming in PostgreSQL...")

        # 1. TPS Tech (Shopify)
        tpstech = session.scalar(select(Store).where(Store.name == "tpstech"))
        if not tpstech:
            tpstech = Store(
                name="tpstech",
                display_name="TPS Tech",
                domain="tpstech.in",
                base_url="https://www.tpstech.in",
                search_endpoint="https://www.tpstech.in/search?q={query}",
                search_config={
                    "platform": "shopify",
                    "page_endpoint": "https://www.tpstech.in/{query}/products.json?limit=250",
                },
                product_config={
                    "platform": "shopify",
                },
            )
            session.add(tpstech)
            session.flush()

        # 2. ModxComputers (Next.js)
        modx = session.scalar(select(Store).where(Store.name == "modxcomputers"))
        if not modx:
            modx = Store(
                name="modxcomputers",
                display_name="ModxComputers",
                domain="modxcomputers.com",
                base_url="https://modxcomputers.com",
                search_endpoint="https://modxcomputers.com/search?q={query}",
                search_config={
                    "platform": "nextjs",
                    "page_endpoint": "https://modxcomputers.com/{query}",
                },
                product_config={
                    "platform": "nextjs",
                },
            )
            session.add(modx)
            session.flush()

        # 3. TLG Gaming (OpenCart)
        tlggaming = session.scalar(select(Store).where(Store.name == "tlggaming"))
        if not tlggaming:
            tlggaming = Store(
                name="tlggaming",
                display_name="TLG Gaming",
                domain="tlggaming.com",
                base_url="https://tlggaming.com",
                search_endpoint="https://tlggaming.com/index.php?route=product/search&search={query}",
                search_config={
                    "platform": "opencart",
                    "page_endpoint": "https://tlggaming.com/{query}&page={page}",
                    "selectors": {
                        "product_card": ".product-layout, .product-thumb",
                        "title": ".name a, h4 a, .title a",
                        "price": ".price-new, .price",
                        "mrp": ".price-old",
                        "image": "img",
                    },
                    "attributes": {
                        "url": "href",
                        "image": "src",
                    },
                },
                product_config={},
            )
            session.add(tlggaming)
            session.flush()

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for store, target_list in [(tpstech, TPSTECH_TARGETS), (modx, MODX_TARGETS), (tlggaming, TLG_TARGETS)]:
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
        print("TPS TECH, MODXCOMPUTERS & TLG GAMING INITIALIZED SUCCESSFULLY IN POSTGRESQL!")


if __name__ == "__main__":
    setup_three_stores()
