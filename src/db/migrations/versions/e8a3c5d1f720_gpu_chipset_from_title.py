"""re-key GPU listings: the title corrects the chipset (W7900, R9700, 9070 GRE, GT 710)

Revision ID: e8a3c5d1f720
Revises: d7f4b2e8a619
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session

revision: str = 'e8a3c5d1f720'
down_revision: Union[str, Sequence[str], None] = 'd7f4b2e8a619'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Owner review 2026-10-08: Radeon PRO W7900/W7800 sat under RX 7900 XT/7800 XT,
    RX 9070 GRE under RX 9070, GT 710/730 under GTX, and the R9700 under two names.
    See matching/gpu_identity.chipset_from_title. Stored extractions, no LLM calls;
    about 17 listings move."""
    from matching.gpu_rekey import rekey_gpus

    session = Session(bind=op.get_bind())
    stats = rekey_gpus(session, dry_run=False)
    session.flush()
    print(f"[gpu_chipset_from_title] {stats}")


def downgrade() -> None:
    # The old keys filed cards under the wrong chip; nothing correct to go back to.
    pass
