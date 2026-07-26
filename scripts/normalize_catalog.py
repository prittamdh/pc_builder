"""
CLI script to normalize and populate category tables for all scraped products.
"""
from db.session import SessionLocal
from services.normalization_service import NormalizationService


def main():
    with SessionLocal() as session:
        service = NormalizationService(session)
        count = service.normalize_all_unclassified(limit=500)
        print(f"[Normalize Catalog] Processed and populated category specs for {count} products.")


if __name__ == "__main__":
    main()
