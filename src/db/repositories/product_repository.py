from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.product import Product


class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, product_id: int) -> Product | None:
        return self.session.get(Product, product_id)

    def get_by_sid_pid(self, sid: int, pid: str) -> Product | None:
        stmt = (
            select(Product)
            .where(
                Product.sid == sid,
                Product.pid == pid,
            )
        )
        return self.session.scalar(stmt)

    def create(
        self,
        *,
        sid: int,
        pid: str,
        name: str,
        product_url: str,
        image_url: str | None = None,
        brand: str | None = None,
        category: str | None = None,
        description: str | None = None,
        specifications: dict | None = None,
        currency: str = "INR",
        current_price: float | None = None,
        current_mrp: float | None = None,
        in_stock: bool | None = None,
    ) -> Product:
        product = Product(
            sid=sid,
            pid=pid,
            name=name,
            product_url=product_url,
            image_url=image_url,
            brand=brand,
            category=category,
            description=description,
            specifications=specifications,
            currency=currency,
            current_price=current_price,
            current_mrp=current_mrp,
            in_stock=in_stock,
        )

        self.session.add(product)
        self.session.flush()

        return product

    def get_or_create(
        self,
        *,
        sid: int,
        pid: str,
        **kwargs,
    ) -> tuple[Product, bool]:
        product = self.get_by_sid_pid(sid, pid)

        if product:
            return product, False

        product = self.create(
            sid=sid,
            pid=pid,
            **kwargs,
        )

        return product, True

    def update(self, product: Product, **fields) -> Product:
        for key, value in fields.items():
            if value is not None:
                setattr(product, key, value)

        self.session.flush()
        return product

    def link_target(self, product_id: int, target_id: int) -> None:
        from db.models.product_target import ProductTarget
        stmt = select(ProductTarget).where(
            ProductTarget.product_id == product_id,
            ProductTarget.target_id == target_id,
        )
        exists = self.session.scalar(stmt)
        if not exists:
            pt = ProductTarget(product_id=product_id, target_id=target_id)
            self.session.add(pt)
            self.session.flush()

    def get_unscraped_products(self, limit: int = 10) -> list[Product]:
        stmt = (
            select(Product)
            .where(
                (Product.description.is_(None)) | (Product.specifications.is_(None))
            )
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def get_product_target_ids(self, product_id: int) -> list[int]:
        from db.models.product_target import ProductTarget
        stmt = select(ProductTarget.target_id).where(ProductTarget.product_id == product_id)
        return list(self.session.scalars(stmt))