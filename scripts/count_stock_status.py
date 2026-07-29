"""
Script to count exact in_stock=True vs in_stock=False products across MDComputers catalog pages.
"""
from scrapers.generic_parser import GenericParser
from scrapers.http_client import HttpClient
from db.session import SessionLocal
from db.repositories.store_repository import StoreRepository


def main():
    with SessionLocal() as session:
        store = StoreRepository(session).get_by_name("mdcomputers")
        if not store:
            return

        parser = GenericParser(store)

        categories = [
            ("catalog/processor", "CPUs"),
            ("catalog/graphics-card", "GPUs"),
            ("catalog/motherboard", "Motherboards"),
            ("catalog/desktop-ram", "RAM"),
        ]

        total_true = 0
        total_false = 0

        with HttpClient() as client:
            for endpoint, name in categories:
                cat_true = 0
                cat_false = 0
                print(f"Scraping '{name}' ({endpoint})...")

                for page in range(1, 10):
                    url = f"{store.base_url}/{endpoint}" if page == 1 else f"{store.base_url}/{endpoint}?page={page}"
                    resp = client.get(url)
                    if resp.status_code != 200:
                        break

                    results = parser.parse_search(resp.text)
                    if not results:
                        break

                    for r in results:
                        if r.in_stock is True:
                            cat_true += 1
                        elif r.in_stock is False:
                            cat_false += 1

                print(f"  -> {name} Total: In-Stock (True) = {cat_true}, Out-Of-Stock (False) = {cat_false}")
                total_true += cat_true
                total_false += cat_false

        print("=" * 70)
        print(f"OVERALL SUMMARY: Total In-Stock (True) = {total_true} | Out-Of-Stock (False) = {total_false}")


if __name__ == "__main__":
    main()
