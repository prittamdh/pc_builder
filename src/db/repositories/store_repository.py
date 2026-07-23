from sqlalchemy import select

from db.models import Store
from db.repositories.base_repository import BaseRepository


class StoreRepository(BaseRepository[Store]):

    def add(self, store: Store) -> None:
        self.session.add(store)

    def get(self, sid: int) -> Store | None:
        stmt = select(Store).where(Store.sid == sid)
        return self.session.scalar(stmt)

    def list(self) -> list[Store]:
        stmt = select(Store)
        return list(self.session.scalars(stmt))