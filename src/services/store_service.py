from sqlalchemy.orm import Session

from db.models import Store
from db.repositories.store_repository import StoreRepository


class StoreService:

    def __init__(self, session: Session):
        self.session = session
        self.repository = StoreRepository(session)

    def create_store(self, **kwargs) -> Store:
        store = Store(**kwargs)

        self.repository.add(store)

        self.session.commit()
        self.session.refresh(store)

        return store

    def get_store(self, sid: int) -> Store | None:
        return self.repository.get(sid)

    def list_stores(self) -> list[Store]:
        return self.repository.list()