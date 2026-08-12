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
        output_file = "data/cpu_canonical_audit_report.txt"
        lines = []

        lines.append("=" * 80)
        lines.append("AUDIT REPORT: CANONICAL CPU GROUPS AND MAPPED RAW TITLES")
        lines.append("=" * 80)

        # Query all canonical CPU parts
        stmt_cp = select(CanonicalPart).where(CanonicalPart.category == 'cpu').order_by(CanonicalPart.canonical_id)
        canonical_cpus = session.scalars(stmt_cp).all()

        total_canonical = len(canonical_cpus)
        lines.append(f"\nTotal Unique Canonical CPU Parts: {total_canonical}")
        lines.append("-" * 80)

        # Query mapped raw titles for each canonical_id
        stmt_products = select(Product.canonical_id, Product.name, Product.sid).where(Product.p_category == 'CPU')
        rows = session.execute(stmt_products).fetchall()

        groups = defaultdict(list)
        for cid, name, sid in rows:
            groups[cid].append(name)

        total_listings = len(rows)
        singleton_count = 0

        for idx, cp in enumerate(canonical_cpus, 1):
            titles = groups.get(cp.canonical_id, [])
            if len(titles) == 1:
                singleton_count += 1

            status_flag = f" [{cp.status}]" if cp.status != "OK" else ""
            lines.append(f"\n[{idx:03d}/{total_canonical:03d}] Canonical Key: '{cp.canonical_id}'{status_flag}")
            lines.append(f"     Brand: {cp.brand} | Key Fields: {cp.key_fields}")
            lines.append(f"     Mapped Listings Count: {len(titles)}")
            lines.append("     Mapped Raw Titles:")
            
            unique_titles = sorted(list(set(titles)))
            for t in unique_titles:
                safe_title = t.encode('ascii', errors='replace').decode('ascii')
                lines.append(f"       - {safe_title}")

        lines.append("\n" + "=" * 80)
        lines.append("AUDIT SUMMARY:")
        lines.append(f"  • Total Scraped Raw CPU Listings:      {total_listings}")
        lines.append(f"  • Total Unique Canonical CPU Parts:    {total_canonical}")
        lines.append(f"  • Singleton Groups (1 Listing):        {singleton_count}")
        lines.append(f"  • Deduplication Collapse Ratio:        {total_listings} raw titles -> {total_canonical} canonical parts")
        lines.append("=" * 80)

        report_content = "\n".join(lines)
        print(report_content)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"\n[Saved] Full audit report saved to: '{output_file}'")


if __name__ == "__main__":
    audit_canonical_groups()
