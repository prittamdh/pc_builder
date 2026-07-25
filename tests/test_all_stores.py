from db.session import SessionLocal
from services.store_service import StoreService


def test_all_stores_have_valid_search_config():
    with SessionLocal() as session:
        stores = StoreService(session).get_all()

        assert len(stores) > 0

        required_selectors = {
            "product_card",
            "title",
            "price",
            "mrp",
            "image",
        }

        required_attributes = {
            "url",
            "image",
        }

        for store in stores:
            config = store.search_config

            assert "selectors" in config
            assert "attributes" in config

            assert required_selectors.issubset(config["selectors"].keys())
            assert required_attributes.issubset(config["attributes"].keys())