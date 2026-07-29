"""
Script to clean and standardize all product PIDs in PostgreSQL database
and deduplicate duplicate product records.
"""
from sqlalchemy import text
from db.session import SessionLocal


def reclean_all_pids():
    with SessionLocal() as session:
        print("Cleaning and deduplicating PIDs in PostgreSQL...")

        # 1. Fetch all products
        products = session.execute(text("SELECT id, sid, pid, product_url FROM products")).fetchall()
        print(f"Total products in database: {len(products)}")

        pid_map = {}  # (sid, new_pid) -> master_id
        duplicates_merged = 0
        updated_pids = 0

        cat_slugs = {
            "processor", "cpu-cooler", "motherboard", "graphics-card",
            "desktop-ram", "internal-hdd", "sata-ssd", "gen3-ssd",
            "gen4-ssd", "gen5-ssd", "monitor", "cabinet", "smps",
            "external-hdd", "external-ssd", "laptop-ram", "ram",
            "storage", "hard-drive"
        }

        # Pass 1: Build existing map of (sid, pid) -> id
        existing_map = {}
        for prod_id, sid, old_pid, _ in products:
            existing_map[(sid, old_pid)] = prod_id

        for prod_id, sid, old_pid, url in products:
            # Skip if already deleted during merge
            check = session.execute(text("SELECT id FROM products WHERE id = :id"), {"id": prod_id}).first()
            if not check:
                continue

            clean_url = str(url).split("?")[0].rstrip("/")

            if "/product/" in clean_url:
                segs = [s for s in clean_url.split("/product/")[1].split("/") if s]
                if segs and segs[0].lower() in cat_slugs and len(segs) > 1:
                    new_pid = segs[-1]
                elif segs and segs[-1].lower() in cat_slugs:
                    new_pid = segs[0]
                elif segs:
                    new_pid = segs[0]
                else:
                    new_pid = clean_url.split("/")[-1]
            elif clean_url:
                new_pid = clean_url.split("/")[-1]
            else:
                new_pid = old_pid

            target_key = (sid, new_pid)

            if target_key in existing_map and existing_map[target_key] != prod_id:
                master_id = existing_map[target_key]
                print(f"  -> Merging duplicate product id={prod_id} into master_id={master_id} (pid={new_pid})")

                session.execute(
                    text("UPDATE price_history SET product_id = :master_id WHERE product_id = :prod_id"),
                    {"master_id": master_id, "prod_id": prod_id}
                )
                session.execute(
                    text("UPDATE product_targets SET product_id = :master_id WHERE product_id = :prod_id AND target_id NOT IN (SELECT target_id FROM product_targets WHERE product_id = :master_id)"),
                    {"master_id": master_id, "prod_id": prod_id}
                )
                session.execute(
                    text("DELETE FROM product_targets WHERE product_id = :prod_id"),
                    {"prod_id": prod_id}
                )
                session.execute(text("DELETE FROM products WHERE id = :id"), {"id": prod_id})
                duplicates_merged += 1
            else:
                if new_pid != old_pid:
                    session.execute(
                        text("UPDATE products SET pid = :new_pid WHERE id = :id"),
                        {"new_pid": new_pid, "id": prod_id}
                    )
                    existing_map[target_key] = prod_id
                    updated_pids += 1

        session.commit()
        print("=" * 70)
        print(f"PID CLEANUP COMPLETE: Updated {updated_pids} PIDs, Merged {duplicates_merged} duplicate rows.")


if __name__ == "__main__":
    reclean_all_pids()
