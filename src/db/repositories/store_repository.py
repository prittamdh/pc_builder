from sqlalchemy import select

from db.models import Store
from db.repositories.base_repository import BaseRepository


class StoreRepository(BaseRepository[Store]):

    def add(self, store: Store) -> None:
        self.session.add(store)

    def get(self, store_id: int) -> Store | None:
        stmt = select(Store).where(Store.id == store_id)
        return self.session.scalar(stmt)

    def get_by_name(self, name: str) -> Store | None:
        stmt = select(Store).where(Store.name == name)
        return self.session.scalar(stmt)

    def get_all(self) -> list[Store]:
        stmt = select(Store)
        return list(self.session.scalars(stmt))

    def get_active(self) -> list[Store]:
        stmt = select(Store).where(Store.active.is_(True))
        return list(self.session.scalars(stmt))