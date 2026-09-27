"""re-key GPU listings: memory size in the key, spelling variants merged

Revision ID: a1c7e5f90b32
Revises: d5e9b3c7a410
Create Date: 2026-09-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session

revision: str = 'a1c7e5f90b32'
down_revision: Union[str, Sequence[str], None] = 'd5e9b3c7a410'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """8GB and 16GB versions of a card shared one model, so a 16GB card's "from" price
    could be the 8GB card's. See matching/gpu_identity.py. Uses each listing's stored
    extraction, no LLM calls; about 1,200 listings, a few seconds."""
    from matching.gpu_rekey import rekey_gpus

    session = Session(bind=op.get_bind())
    stats = rekey_gpus(session, dry_run=False)
    session.flush()
    print(f"[rekey_gpu_identity] {stats}")


def downgrade() -> None:
    # The old keys merged different cards; there is nothing correct to go back to.
    # New extractions keep using the new keys either way.
    pass
