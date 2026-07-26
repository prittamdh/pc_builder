from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from common.enums.schedule_type import ScheduleType
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

    def mark_scraped(self, target: ScrapeTarget):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        target.last_scraped_at = now

        if target.schedule_type == int(ScheduleType.HOURLY):
            target.next_scrape_at = now + timedelta(hours=1)
        else:
            target.next_scrape_at = now + timedelta(days=1)

        self.session.commit()