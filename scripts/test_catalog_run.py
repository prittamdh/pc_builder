"""
Test run on MDComputers catalog categories:
1. catalog/processor (CPU)
2. catalog/graphics-card (GPU)
Inspects all extracted data fields, including exact in_stock boolean values.
"""
from scrapers.generic_parser import GenericParser
from scrapers.http_client import HttpClient
from db.session import SessionLocal
from db.repositories.store_repository import StoreRepository


def main():
    with SessionLocal() as session:
        store = StoreRepository(session).get_by_name("mdcomputers")
        if not store:
            print("[Error] MDComputers store configuration not found.")
            return

        categories_to_test = [
            ("catalog/processor", "CPU"),
            ("catalog/graphics-card", "GPU"),
        ]

        parser = GenericParser(store)

        with HttpClient() as client:
            for endpoint, cat_name in categories_to_test:
                print("=" * 80)
                print(f"TEST RUN: Scraped MDComputers Catalog Target '{endpoint}' ({cat_name})")
                print("=" * 80)

                for page in range(1, 3):
                    url = f"{store.base_url}/{endpoint}" if page == 1 else f"{store.base_url}/{endpoint}?page={page}"
                    print(f"\nFetching Page {page}: {url}")

                    resp = client.get(url)
                    print(f"  -> HTTP Status: {resp.status_code}, Length: {len(resp.text)} bytes")

                    # Parse search results
                    results = parser.parse_search(resp.text)
                    print(f"  -> Extracted {len(results)} items from page {page}:")

                    for idx, item in enumerate(results[:5], 1):
                        print(f"     [{idx}] Name: {item.name[:65]}")
                        print(f"         PID: {item.pid}")
                        print(f"         Price: Rs.{item.price:,.2f} | MRP: {f'Rs.{item.mrp:,.2f}' if item.mrp else 'N/A'}")
                        print(f"         In Stock: {item.in_stock}")
                        print(f"         URL: {item.url}")
                        print(f"         Image: {item.image}\n")


if __name__ == "__main__":
    main()
