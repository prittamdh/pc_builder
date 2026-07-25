from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.product import Product


class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, product_id: int) -> Product | None:
        return self.session.get(Product, product_id)

    def get_by_store_and_url(
        self,
        store_id: int,
        product_url: str,
    ) -> Product | None:
        stmt = (
            select(Product)
            .where(
                Product.store_id == store_id,
                Product.product_url == product_url,
            )
        )

        return self.session.scalar(stmt)

    def create(
        self,
        *,
        store_id: int,
        external_id: str | None,
        name: str,
        product_url: str,
        image_url: str | None,
        brand: str | None,
        category: str | None,
    ) -> Product:
        product = Product(
            store_id=store_id,
            external_id=external_id,
            name=name,
            product_url=product_url,
            image_url=image_url,
            brand=brand,
            category=category,
        )

        self.session.add(product)
        self.session.flush()

        return product

    def get_or_create(
        self,
        *,
        store_id: int,
        external_id: str | None,
        name: str,
        product_url: str,
        image_url: str | None,
        brand: str | None,
        category: str | None,
    ) -> Product:

        product = self.get_by_store_and_url(
            store_id,
            product_url,
        )

        if product:
            return product

        return self.create(
            store_id=store_id,
            external_id=external_id,
            name=name,
            product_url=product_url,
            image_url=image_url,
            brand=brand,
            category=category,
        )