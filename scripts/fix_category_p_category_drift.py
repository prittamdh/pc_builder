"""
One-off remediation: products whose p_category disagrees with what
CategoryClassifier.get_p_category() computes from their raw store category + title
(discovered while investigating the GPU-in-CPU leak). For each mismatched product:
  1. delete its stale title-extraction row from the WRONG category's extraction table
  2. clear canonical_id / reset spec_status so it re-enters the correct pipeline
  3. update p_category to the correct value
  4. delete the old canonical_parts row if nothing else references it
Re-runnable (idempotent): a product only shows up here while its p_category is wrong.
"""
import sys

from sqlalchemy import text

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.session import SessionLocal
from matching.category_classifier import CategoryClassifier

EXTRACTION_TABLE = {
    "CPU": "cpu_title_extractions",
    "GPU": "gpu_title_extractions",
    "RAM": "ram_title_extractions",
    "Storage": "storage_title_extractions",
    "Cabinet": "cabinet_title_extractions",
    "Power Supply": "psu_title_extractions",
    "CPU Cooler": "cooler_title_extractions",
    "Monitor": "monitor_title_extractions",
    "Motherboard": "motherboard_title_extractions",
}


def main(dry_run: bool = True):
    with SessionLocal() as s:
        rows = s.execute(text(
            "SELECT id, category, name, p_category, canonical_id FROM products WHERE category IS NOT NULL"
        )).fetchall()

        changed = []
        for pid, raw_cat, name, old_pcat, canon in rows:
            new_pcat = CategoryClassifier.get_p_category(raw_cat, name)
            if new_pcat != old_pcat:
                changed.append((pid, raw_cat, name, old_pcat, new_pcat, canon))

        print(f"{len(changed)} products need p_category correction")
        by_pair = {}
        for pid, raw_cat, name, old_pcat, new_pcat, canon in changed:
            by_pair.setdefault((old_pcat, new_pcat), []).append(pid)
        for (old_pcat, new_pcat), ids in sorted(by_pair.items()):
            print(f"  {old_pcat} -> {new_pcat}: {len(ids)} products")

        if dry_run:
            print("\nDRY RUN - no changes made. Re-run with dry_run=False to apply.")
            return

        touched_new_categories = set()
        old_canonical_ids_to_check = set()

        for pid, raw_cat, name, old_pcat, new_pcat, canon in changed:
            old_table = EXTRACTION_TABLE.get(old_pcat)
            if old_table:
                s.execute(text(f"DELETE FROM {old_table} WHERE product_id = :pid"), {"pid": pid})

            s.execute(
                text("UPDATE products SET p_category = :new_pcat, canonical_id = NULL, spec_status = 'pending' WHERE id = :pid"),
                {"new_pcat": new_pcat, "pid": pid},
            )

            if canon:
                old_canonical_ids_to_check.add(canon)
            touched_new_categories.add(new_pcat)

        s.commit()

        orphans_deleted = 0
        for canon in old_canonical_ids_to_check:
            still_used = s.execute(
                text("SELECT 1 FROM products WHERE canonical_id = :c LIMIT 1"), {"c": canon}
            ).fetchone()
            if not still_used:
                s.execute(text("DELETE FROM canonical_parts WHERE canonical_id = :c"), {"c": canon})
                orphans_deleted += 1
        s.commit()

        print(f"\nUpdated {len(changed)} products.")
        print(f"Deleted {orphans_deleted} orphaned canonical_parts rows.")
        print(f"Categories now needing re-extraction: {sorted(touched_new_categories)}")


if __name__ == "__main__":
    main(dry_run="--apply" not in sys.argv)
