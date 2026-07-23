from sqlalchemy import select, func

from db.models import ScrapeTarget
from db.repositories.base_repository import BaseRepository


class ScrapeTargetRepository(BaseRepository[ScrapeTarget]):

    def add(self, scrape_target: ScrapeTarget) -> None:
        self.session.add(scrape_target)

    def get(self, tid: int) -> ScrapeTarget | None:
        stmt = select(ScrapeTarget).where(
            ScrapeTarget.tid == tid
        )
        return self.session.scalar(stmt)

    def list_active(self) -> list[ScrapeTarget]:
        stmt = (
            select(ScrapeTarget)
            .where(ScrapeTarget.enabled.is_(True))
            .order_by(ScrapeTarget.priority.desc())
        )

        return list(self.session.scalars(stmt))

    def get_due_targets(
        self,
        limit: int = 10,
    ) -> list[ScrapeTarget]:

        stmt = (
            select(ScrapeTarget)
            .where(
                ScrapeTarget.enabled.is_(True),
                ScrapeTarget.next_scrape_at <= func.now(),
            )
            .order_by(
                ScrapeTarget.priority.desc(),
                ScrapeTarget.next_scrape_at,
            )
            .limit(limit)
        )

        return list(self.session.scalars(stmt))