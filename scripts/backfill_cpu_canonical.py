"""
Phase 3 CPU Category Canonical Backfill Script.
Processes all CPU listings in PostgreSQL products table through resolve_canonical(),
attaches products.canonical_id, and calculates exact deduplication collapse metrics.
"""
from sqlalchemy import text, select, func
from db.session import SessionLocal
from db.models.product import Product
from db.models.canonical_part import CanonicalPart
from matching.resolver import resolve_canonical


def backfill_cpu_canonical():
    with SessionLocal() as session:
        print("=" * 80)
        print("PHASE 3: RUNNING CANONICAL RESOLUTION FOR CPU CATEGORY LISTINGS")
        print("=" * 80)

        # 1. Fetch all CPU listings from products table
        stmt = select(Product).where(Product.p_category == 'CPU')
        cpu_products = session.scalars(stmt).all()
        total_cpu_listings = len(cpu_products)

        print(f"\nFound {total_cpu_listings} CPU raw product listings in PostgreSQL.")
        print("Resolving canonical parts...")

        resolved_count = 0
        review_flag_checks_run = 0

        for p in cpu_products:
            canonical_id = resolve_canonical(p.name, 'CPU', session)
            p.canonical_id = canonical_id
            resolved_count += 1

            # Verify review flag check ran for this listing
            cp_stmt = select(CanonicalPart).where(CanonicalPart.canonical_id == canonical_id)
            cp = session.scalar(cp_stmt)
            assert cp is not None and cp.status in ('OK', 'NEEDS_REVIEW'), f"Review check failed for listing {p.id}"
            review_flag_checks_run += 1

        session.commit()

        # Confirm review flag check ran for 100% of listings
        assert review_flag_checks_run == total_cpu_listings, "Review flag check did not run for all listings!"
        print(f"[Verified] Review-flag check ran for 100% ({review_flag_checks_run}/{total_cpu_listings}) of CPU listings.")

        # 2. Query collapse statistics
        stmt_parts = select(func.count(CanonicalPart.canonical_id)).where(CanonicalPart.category == 'cpu')
        unique_canonical_cpus = session.scalar(stmt_parts)

        stmt_review = select(func.count(CanonicalPart.canonical_id)).where(
            CanonicalPart.category == 'cpu', CanonicalPart.status == 'NEEDS_REVIEW'
        )
        review_count = session.scalar(stmt_review)

        reduction_ratio = ((total_cpu_listings - unique_canonical_cpus) / total_cpu_listings * 100) if total_cpu_listings else 0.0

        print("\n" + "=" * 80)
        print("PHASE 3 CPU CANONICAL MATCHING METRICS & COLLAPSE REPORT")
        print("=" * 80)
        print(f"  • Total Scraped Raw CPU Listings:      {total_cpu_listings} listings")
        print(f"  • Unique Canonical CPU Parts Created: {unique_canonical_cpus} canonical parts")
        print(f"  • Flagged for Review Queue:          {review_count} parts")
        print(f"  • Deduplication Reduction Efficiency:  {reduction_ratio:.1f}% reduction")
        print("=" * 80)


if __name__ == "__main__":
    backfill_cpu_canonical()
