"""
Canonical Groups Audit Script.
Queries PostgreSQL database for canonical CPU parts and lists all raw products.name titles that mapped to each part.
Enables manual inspection for False Merges (different CPUs collapsed together) and False Splits (same CPU split into multiple canonical parts).
"""
from collections import defaultdict
from sqlalchemy import text, select
from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart


def audit_canonical_groups():
    with SessionLocal() as session:
        print("=" * 80)
        print("AUDIT REPORT: CANONICAL CPU GROUPS AND MAPPED RAW TITLES")
        print("=" * 80)

        # Query all canonical CPU parts
        stmt_cp = select(CanonicalPart).where(CanonicalPart.category == 'cpu').order_by(CanonicalPart.canonical_id)
        canonical_cpus = session.scalars(stmt_cp).all()

        total_canonical = len(canonical_cpus)
        print(f"\nTotal Unique Canonical CPU Parts: {total_canonical}")
        print("-" * 80)

        # Query mapped raw titles for each canonical_id
        stmt_products = select(Product.canonical_id, Product.name, Product.sid).where(Product.p_category == 'CPU')
        rows = session.execute(stmt_products).fetchall()

        groups = defaultdict(list)
        for cid, name, sid in rows:
            groups[cid].append(name)

        total_listings = len(rows)

        for idx, cp in enumerate(canonical_cpus, 1):
            titles = groups.get(cp.canonical_id, [])
            status_flag = f" [{cp.status}]" if cp.status != "OK" else ""
            print(f"\n[{idx:02d}/{total_canonical:02d}] Canonical Key: '{cp.canonical_id}'{status_flag}")
            print(f"     Brand: {cp.brand} | Key Fields: {cp.key_fields}")
            print(f"     Mapped Listings Count: {len(titles)}")
            print("     Mapped Raw Titles:")
            # Display unique raw titles mapped to this key
            unique_titles = sorted(list(set(titles)))
            for t in unique_titles:
                safe_title = t.encode('ascii', errors='replace').decode('ascii')
                print(f"       - {safe_title}")

        print("\n" + "=" * 80)
        print("AUDIT SUMMARY:")
        print(f"  • Total Scraped Raw CPU Listings:      {total_listings}")
        print(f"  • Total Unique Canonical CPU Parts:    {total_canonical}")
        print(f"  • Deduplication Collapse Ratio:        {total_listings} raw titles -> {total_canonical} canonical parts")
        print("=" * 80)


if __name__ == "__main__":
    audit_canonical_groups()
