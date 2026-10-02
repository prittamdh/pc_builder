"""re-check every listing's condition: OEM/tray added, only new stock is listed

Revision ID: c3e1a9d7b552
Revises: b2d8f6a1c043
Create Date: 2026-10-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3e1a9d7b552'
down_revision: Union[str, Sequence[str], None] = 'b2d8f6a1c043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Owner decision 2026-10-02: only new, retail-boxed stock is listed. Condition is
    read from the title when a listing is saved; this applies the new OEM/tray rule
    to listings saved before it. Titles only, no fetching."""
    from matching.condition_policy import detect_condition

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, name, p_category, condition FROM products")).all()
    changed = [
        {"id": r.id, "c": new}
        for r in rows
        if (new := detect_condition(r.name, r.p_category)) != r.condition
    ]
    if changed:
        bind.execute(sa.text("UPDATE products SET condition = :c WHERE id = :id"), changed)
    print(f"[recheck_listing_condition] {len(rows)} listings, {len(changed)} changed")


def downgrade() -> None:
    pass
