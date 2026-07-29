"""
Script to enforce 100% granular categories across all products in PostgreSQL.
Eliminates all generic 'Accessories', 'CPU', 'GPU' umbrella clubbing.
"""
from sqlalchemy import text
from db.session import SessionLocal


def classify_title(title: str, current_cat: str) -> str:
    t = title.lower()

    # Processors
    if "ryzen" in t or "intel core" in t or "i3-" in t or "i5-" in t or "i7-" in t or "i9-" in t or "ultra 5" in t or "ultra 7" in t or "ultra 9" in t or "threadripper" in t or "processor" in t:
        if "cooler" not in t and "fan" not in t and "motherboard" not in t:
            if "threadripper" in t:
                return "Threadripper Processor"
            if "intel" in t or "i3-" in t or "i5-" in t or "i7-" in t or "i9-" in t or "ultra" in t:
                return "Intel Processor"
            if "ryzen" in t or "amd" in t:
                return "AMD Processor"
            return "Processor"

    # Motherboards
    if "motherboard" in t or "mobo" in t or "b450" in t or "b550" in t or "b650" in t or "x570" in t or "x670" in t or "h610" in t or "b760" in t or "z790" in t or "z890" in t:
        if "intel" in t or "h610" in t or "b760" in t or "z790" in t or "z890" in t or "lga" in t:
            return "Intel Motherboard"
        if "amd" in t or "b450" in t or "b550" in t or "b650" in t or "x570" in t or "x670" in t or "am4" in t or "am5" in t:
            return "AMD Motherboard"
        return "Motherboard"

    # Graphics Cards
    if "geforce" in t or "radeon" in t or "graphics card" in t or "rtx" in t or "gtx" in t or "rx " in t or "gpu" in t:
        if "rtx 50" in t:
            return "NVIDIA RTX 50 Series"
        if "rtx 40" in t:
            return "NVIDIA RTX 40 Series"
        if "rtx 30" in t:
            return "NVIDIA RTX 30 Series"
        if "radeon" in t or "rx " in t:
            return "AMD Graphics Card"
        if "geforce" in t or "nvidia" in t or "rtx" in t or "gtx" in t:
            return "Graphics Card (NVIDIA)"
        return "Graphics Card"

    # RAM
    if "ddr4" in t or "ddr5" in t or "ram" in t or "memory" in t or "desktop memory" in t or "laptop memory" in t:
        if "laptop" in t or "so-dimm" in t or "sodimm" in t:
            if "ddr5" in t:
                return "Laptop RAM (DDR5)"
            if "ddr4" in t:
                return "Laptop RAM (DDR4)"
            return "Laptop RAM"
        if "ddr5" in t:
            return "Desktop RAM (DDR5)"
        if "ddr4" in t:
            return "Desktop RAM (DDR4)"
        return "Desktop RAM"

    # Storage (SSDs & HDDs)
    if "nvme" in t or "ssd" in t or "m.2" in t or "hard drive" in t or "hdd" in t or "solid state" in t:
        if "hdd" in t or "hard drive" in t or "hard disk" in t:
            if "external" in t or "portable" in t:
                return "External HDD"
            return "Internal HDD"
        if "external" in t or "portable" in t:
            return "External SSD"
        if "gen5" in t:
            return "Gen5 NVMe SSD"
        if "gen4" in t:
            return "Gen4 NVMe SSD"
        if "m.2" in t or "nvme" in t:
            return "M.2 NVMe SSD"
        if "sata" in t:
            return "2.5\" SATA SSD"
        return "SSD"

    # Cooling
    if "cooler" in t or "cooling" in t or "liquid cooler" in t or "air cooler" in t or "aio" in t or "fan" in t or "thermal paste" in t:
        if "liquid" in t or "aio" in t:
            return "CPU Liquid Cooler"
        if "air" in t:
            return "CPU Air Cooler"
        return "CPU Cooler"

    # Power Supply
    if "power supply" in t or "psu" in t or "smps" in t or "watt" in t or " 80+" in t or "80 plus" in t:
        return "Power Supply / SMPS"

    # Cabinets
    if "cabinet" in t or "case" in t or "chassis" in t or "tower" in t:
        return "Cabinet"

    # Monitors
    if "monitor" in t or "display" in t or "screen" in t or "hz" in t or "curved" in t:
        return "Monitor"

    # Peripherals
    if "keyboard" in t:
        return "Keyboard"
    if "mouse" in t and "pad" not in t:
        return "Mouse"
    if "headset" in t or "headphone" in t or "earphone" in t:
        return "Headset"
    if "webcam" in t or "camera" in t:
        return "Webcam"

    return current_cat


def enforce_granular_categories():
    with SessionLocal() as session:
        print("Enforcing 100% granular categories across PostgreSQL products...")

        # 1. Update from product_targets -> scrape_targets.schedule_config['category']
        sql1 = text("""
            UPDATE products p
            SET category = st.schedule_config->>'category'
            FROM product_targets pt
            JOIN scrape_targets st ON pt.target_id = st.id
            WHERE p.id = pt.product_id
              AND st.schedule_config->>'category' IS NOT NULL;
        """)
        res1 = session.execute(sql1)
        print(f"  Updated {res1.rowcount} products directly from ScrapeTarget granular categories.")

        # 2. Refine remaining generic categories (Accessories, CPU, GPU, etc.) based on title matching
        sql2 = text("SELECT id, name, category FROM products WHERE category IN ('Accessories', 'CPU', 'GPU', 'RAM', 'SSD', 'PSU');")
        rows = session.execute(sql2).fetchall()

        updated_count = 0
        for pid, title, cat in rows:
            new_cat = classify_title(title, cat)
            if new_cat != cat:
                session.execute(text("UPDATE products SET category = :nc WHERE id = :pid"), {"nc": new_cat, "pid": pid})
                updated_count += 1

        session.commit()
        print(f"  Re-classified {updated_count} generic products based on granular title matching.")
        print("=" * 80)
        print("GRANULAR CATEGORY ENFORCEMENT COMPLETE!")


if __name__ == "__main__":
    enforce_granular_categories()
