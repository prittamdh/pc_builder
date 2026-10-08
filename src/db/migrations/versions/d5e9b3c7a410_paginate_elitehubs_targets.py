"""paginate EliteHubs targets: max_pages 1 -> 10

Revision ID: d5e9b3c7a410
Revises: c8a4f2e6b193
Create Date: 2026-09-25 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd5e9b3c7a410'
down_revision: Union[str, Sequence[str], None] = 'c8a4f2e6b193'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Shopify pages now carry 100 products, not 250 (request_planner.SHOPIFY_PAGE_SIZE),
    so the 5 MB upload cap holds. EliteHubs targets were capped at 1 page, which at 250
    a page already cut six categories off at exactly 250 products. 10 pages covers up
    to 1,000; pagination still stops at the first page with nothing new."""
    op.execute("""
        UPDATE scrape_targets t
        SET schedule_config = jsonb_set(t.schedule_config, '{max_pages}', '10')
        FROM stores s
        WHERE s.id = t.store_id AND s.name = 'elitehubs'
          AND (t.schedule_config->>'max_pages')::int = 1
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE scrape_targets t
        SET schedule_config = jsonb_set(t.schedule_config, '{max_pages}', '1')
        FROM stores s
        WHERE s.id = t.store_id AND s.name = 'elitehubs'
          AND (t.schedule_config->>'max_pages')::int = 10
    """)
