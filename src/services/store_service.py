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

    def get(self, store_id: int) -> Store | None:
        return self.repository.get(store_id)

    def get_by_name(self, name: str) -> Store |None:
        return self.repository.get_by_name(name)

    def get_all(self) -> list[Store]:
        return self.repository.get_all()

    def get_active(self) -> list[Store]:
        return self.repository.get_active()