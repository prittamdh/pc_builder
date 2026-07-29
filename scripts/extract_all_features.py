"""
Batch Feature Extraction Script.
Extracts typed, structured specifications across all 11,048 products in PostgreSQL
and populates the 9 relational specification tables:
- cpu_specs
- gpu_specs
- motherboard_specs
- ram_specs
- ssd_specs
- psu_specs
- cabinet_specs
- cooler_specs
- monitor_specs
"""
from db.session import SessionLocal
from sqlalchemy import text
from db.models.product import Product
from services.normalization_service import NormalizationService


def extract_all_features():
    with SessionLocal() as session:
        print("Starting 100% Feature Extraction across all PostgreSQL products...")
        products = session.query(Product).all()
        total = len(products)
        print(f"  Loaded {total} products for specification feature extraction...")

        norm_service = NormalizationService(session)
        processed = 0

        for p in products:
            try:
                norm_service.normalize_product(p)
                processed += 1
                if processed % 1000 == 0:
                    print(f"  Processed {processed}/{total} products...")
            except Exception as e:
                print(f"  Error extracting features for product ID {p.id}: {e}")

        session.commit()
        print("=" * 80)
        print(f"SUCCESSFULLY EXTRACTED SPECIFICATION FEATURES FOR {processed} PRODUCTS!")


if __name__ == "__main__":
    extract_all_features()
