from sqlalchemy.orm import Session

from db.session import engine
from db.models.store import Store


STORES = [
    {
        "name": "mdcomputers",
        "display_name": "MDComputers",
        "domain": "mdcomputers.in",
        "base_url": "https://mdcomputers.in",

        # Generic search endpoint
        "search_endpoint": "https://mdcomputers.in/catalogsearch/result/?q={query}",

        "currency": "INR",
        "currency_symbol": "₹",

        "search_config": {
            "selectors": {
                "product_card": "div.product-grid-item",
                "title": "h3.product-entities-title a",
                "price": "span.ins",
                "mrp": "span.del",
                "image": "img",
            },
            "attributes": {
                "url": "href",
                "image": "src",
            },
        },

        "product_config": {},

        "active": True,
    }
]


def main():
    with Session(engine) as session:
        for store in STORES:
            exists = (
                session.query(Store)
                .filter(Store.name == store["name"])
                .first()
            )

            if exists:
                print(f"Updating {store['name']}")

                for key, value in store.items():
                    setattr(exists, key, value)
            else:
                print(f"Creating {store['name']}")
                session.add(Store(**store))

        session.commit()

    print("Store seeding completed.")


if __name__ == "__main__":
    main()