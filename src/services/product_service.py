from sqlalchemy.orm import Session

from db.repositories.product_repository import ProductRepository
from domain.product import Product


class ProductService:
    def __init__(self, session: Session):
        self.session = session
        self.product_repository = ProductRepository(session)

    def save(self, product: Product):
        db_product = self.product_repository.get_by_sid_pid(
            sid=product.sid,
            pid=product.pid,
        )

        if db_product is None:
            db_product = self.product_repository.create(
                sid=product.sid,
                pid=product.pid,
                name=product.name,
                product_url=str(product.url),
                image_url=str(product.image) if product.image else None,
                brand=product.brand,
                category=product.category,
                description=product.description,
                specifications=product.specifications,
                currency=product.currency,
                current_price=float(product.price) if product.price is not None else None,
                current_mrp=float(product.mrp) if product.mrp is not None else None,
                in_stock=product.in_stock,
            )
        else:
            self.product_repository.update(
                db_product,
                name=product.name,
                product_url=str(product.url),
                image_url=str(product.image) if product.image else None,
                brand=product.brand,
                category=product.category,
                description=product.description,
                specifications=product.specifications,
                currency=product.currency,
                current_price=float(product.price) if product.price is not None else None,
                current_mrp=float(product.mrp) if product.mrp is not None else None,
                in_stock=product.in_stock,
            )

        self.session.commit()
        return db_product