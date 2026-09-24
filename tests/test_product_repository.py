"""SearchService.save passes every field below to ProductRepository.create for a new listing.

A 2026-09-02 change added `condition` to the call but not to create(), so every scrape
batch holding a new product raised TypeError and rolled back - and the DAG caught and
printed it, so runs kept reporting success while no prices were saved for 38 days.
"""
from db.repositories.product_repository import ProductRepository


class _Session:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def test_create_accepts_every_field_search_service_sends():
    repo = ProductRepository.__new__(ProductRepository)
    repo.session = _Session()
    product = repo.create(
        sid=1, pid="x", name="Ant Esports ICE-100 Open Box", product_url="https://example.in/p",
        image_url=None, category="Cabinet", p_category="Cabinet", condition="open_box",
        currency="INR", current_price=999.0, current_mrp=None, in_stock=True,
    )
    assert product.condition == "open_box"
