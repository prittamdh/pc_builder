from sqlalchemy.orm import Session

from db.repositories.product_repository import ProductRepository
from db.repositories.price_history_repository import PriceHistoryRepository
from db.models.product import Product as ProductDomain


class ProductService:
    def __init__(self, session: Session):
        self.session = session
        self.product_repository = ProductRepository(session)
        self.price_history_repository = PriceHistoryRepository(session)

    def save(
        self,
        *,
        store_id: int,
        product: ProductDomain,
        category: str | None = None,
    ):
        db_product = self.product_repository.get_or_create(
            store_id=store_id,
            external_id=product.sku,
            name=product.name,
            product_url=product.url,
            image_url=product.image,
            brand=product.brand,
            category=category,
        )

        self.price_history_repository.create(
            product_id=db_product.id,
            price=product.price,
            mrp=product.mrp,
            in_stock=product.in_stock,
        )

        self.session.commit()

        return db_product