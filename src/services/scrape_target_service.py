from sqlalchemy.orm import Session

from db.models import ScrapeTarget
from db.repositories.scrape_target_repository import (
    ScrapeTargetRepository,
)


class ScrapeTargetService:

    def __init__(self, session: Session):
        self.session = session
        self.repository = ScrapeTargetRepository(session)

    def create_target(self, **kwargs) -> ScrapeTarget:
        target = ScrapeTarget(**kwargs)

        self.repository.add(target)

        self.session.commit()
        self.session.refresh(target)

        return target

    def get_target(self, tid: int) -> ScrapeTarget | None:
        return self.repository.get(tid)

    def list_active(self) -> list[ScrapeTarget]:
        return self.repository.list_active()

    def get_due_targets(
        self,
        limit: int = 10,
    ) -> list[ScrapeTarget]:
        return self.repository.get_due_targets(limit)