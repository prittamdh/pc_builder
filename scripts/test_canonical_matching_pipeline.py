"""
Standalone runner to test the experimental canonical matching pipeline on 10-store database data.
Uses scripts/normalize.py, scripts/schemas.py, and scripts/match.py WITHOUT altering them.
Stores results in canonical_products_test and store_listings_test.
"""
from db.session import SessionLocal
from services.canonical_matching_service import CanonicalMatchingService


def main():
    print("=" * 80)
    print("STARTING TEST RUN FOR CANONICAL MATCHING PIPELINE")
    print("=" * 80)

    with SessionLocal() as session:
        service = CanonicalMatchingService(session)
        summary = service.run_experimental_matching()

        print("\n" + "=" * 80)
        print("SAMPLE CANONICAL PRODUCT GROUPS (MATCHED ACROSS MULTIPLE STORES)")
        print("=" * 80)

        # Query top matched canonical products with >1 store listings
        products = service.get_canonical_products(limit=100)
        multi_store_groups = [p for p in products if len(p.get("listings", [])) > 1]

        print(f"Found {len(multi_store_groups)} multi-store matched canonical product groups!")
        print("-" * 80)

        for p in multi_store_groups[:15]:
            print(f"\n[Canonical Product ID {p['id']}] Category: {p['category'].upper()} | Key: '{p['canonical_key']}'")
            print(f"  Canonical Name: '{p['name']}'")
            print(f"  Extracted Attributes: {p['attributes']}")
            print(f"  Listings ({len(p['listings'])} stores):")
            for lst in p['listings']:
                price_str = f"{float(lst['price']):,.2f}" if lst.get('price') else 'N/A'
                print(f"    - [{lst['store_name']}] INR {price_str} | {lst['raw_title']}")


if __name__ == "__main__":
    main()
