from sqlalchemy.orm import Session

from db.models.price_history import PriceHistory


class PriceHistoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        product_id: int,
        price: float,
        mrp: float | None,
        in_stock: bool,
    ) -> PriceHistory:
        history = PriceHistory(
            product_id=product_id,
            price=price,
            mrp=mrp,
            in_stock=in_stock,
        )

        self.session.add(history)
        self.session.flush()

        return history