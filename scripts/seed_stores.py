from sqlalchemy.orm import Session

from db.session import engine
from db.models.store import Store


STORES = [
    {
        "name": "mdcomputers",
        "display_name": "MDComputers",
        "domain": "mdcomputers.in",
        "base_url": "https://mdcomputers.in",
        "search_endpoint": "https://mdcomputers.in/catalogsearch/result/?q={query}",
        "currency": "INR",
        "currency_symbol": "₹",
        "search_config": {
            "page_endpoint": "https://mdcomputers.in/catalogsearch/result/index/?p={page}&q={query}",
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
    },
    {
        "name": "pcstudio",
        "display_name": "PCStudio",
        "domain": "pcstudio.in",
        "base_url": "https://www.pcstudio.in",
        "search_endpoint": "https://www.pcstudio.in/?s={query}&post_type=product",
        "currency": "INR",
        "currency_symbol": "₹",
        "search_config": {
            "page_endpoint": "https://www.pcstudio.in/page/{page}/?s={query}&post_type=product",
            "selectors": {
                "product_card": "ul.products > li.product",
                "title": "li.title a",
                "price": "ins .woocommerce-Price-amount, .price .woocommerce-Price-amount",
                "mrp": "del .woocommerce-Price-amount",
                "image": "img",
            },
            "attributes": {
                "url": "href",
                "image": "src",
            },
        },
        "product_config": {},
        "active": True,
    },
    {
        "name": "vedant",
        "display_name": "Vedant Computers",
        "domain": "vedantcomputers.com",
        "base_url": "https://www.vedantcomputers.com",
        "search_endpoint": "https://www.vedantcomputers.com/index.php?route=product/search&search={query}",
        "currency": "INR",
        "currency_symbol": "₹",
        "search_config": {
            "page_endpoint": "https://www.vedantcomputers.com/index.php?route=product/search&search={query}&page={page}",
            "selectors": {
                "product_card": ".main-products .product-layout",
                "title": ".name a",
                "price": ".price-new, .price",
                "mrp": ".price-old",
                "image": ".product-img img",
            },
            "attributes": {
                "url": "href",
                "image": "data-src",
            },
        },
        "product_config": {
            "title": "h1, .product-title h1",
            "price": ".price-new, .price",
            "mrp": ".price-old",
            "image": ".product-image img, .product-image-main img, .swiper-slide-active img",
            "description": "#tab-description, .tab-pane, .product-description",
        },
        "active": True,
    },
    {
        "name": "primeabgb",
        "display_name": "PrimeABGB",
        "domain": "primeabgb.com",
        "base_url": "https://www.primeabgb.com",
        "search_endpoint": "https://www.primeabgb.com/?s={query}&post_type=product",
        "currency": "INR",
        "currency_symbol": "₹",
        "search_config": {
            "page_endpoint": "https://www.primeabgb.com/page/{page}/?s={query}&post_type=product",
            "selectors": {
                "product_card": ".product",
                "title": ".product-title",
                "price": ".price .woocommerce-Price-amount",
                "mrp": "del .woocommerce-Price-amount",
                "image": ".product-image img",
            },
            "attributes": {
                "url": "href",
                "image": "src",
            },
        },
        "product_config": {
            "title": "h1.product_title",
            "price": ".summary .price ins .woocommerce-Price-amount, .summary .price > .woocommerce-Price-amount",
            "mrp": ".summary .price del .woocommerce-Price-amount",
            "image": ".woocommerce-product-gallery img",
            "description": "#tab-description, .woocommerce-Tabs-panel--description",
        },
        "active": True,
    },
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