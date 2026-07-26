from decimal import Decimal

from sqlalchemy.orm import Session

from db.models.price_history import PriceHistory
from db.repositories.product_repository import ProductRepository
from domain.search_result import SearchResult


class SearchService:
    def __init__(self, session: Session):
        self.session = session
        self.product_repository = ProductRepository(session)

    def save(self, result: SearchResult, target_id: int | None = None):
        product, created = self.product_repository.get_or_create(
            sid=result.sid,
            pid=result.pid,
            name=result.name,
            product_url=str(result.url),
            image_url=str(result.image) if result.image else None,
            currency=result.currency,
            current_price=float(result.price),
            current_mrp=float(result.mrp) if result.mrp is not None else None,
            in_stock=result.in_stock,
        )

        if not created:
            self.product_repository.update(
                product,
                name=result.name,
                product_url=str(result.url),
                image_url=str(result.image) if result.image else None,
                currency=result.currency,
                current_price=float(result.price),
                current_mrp=float(result.mrp) if result.mrp is not None else None,
                in_stock=result.in_stock,
            )

        if target_id is not None:
            self.product_repository.link_target(product.id, target_id)

        price_history = PriceHistory(
            product_id=product.id,
            price=Decimal(result.price),
            mrp=Decimal(result.mrp) if result.mrp is not None else None,
            in_stock=result.in_stock if result.in_stock is not None else True,
        )

        self.session.add(price_history)

    def save_many(self, results: list[SearchResult], target_id: int | None = None):
        for result in results:
            self.save(result, target_id=target_id)

        self.session.commit()