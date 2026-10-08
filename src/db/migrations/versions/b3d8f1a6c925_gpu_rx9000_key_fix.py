"""Re-key the PowerColor Hellhound Spectral White RX 9060 XT, read as "RX 9000"

The extractor took the chip as "RX 9000", so the listing was keyed
gpu:powercolor:rx_9000:16gb:hellhound_spectral_white, matched nothing else and got
no board power. The title says RX 9060 XT (RX9060XT-16G-L-OC-WHITE). Applied to the
local copy of live first.

Revision ID: b3d8f1a6c925
Revises: b82c3fbf011a
Create Date: 2026-10-08 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session

revision: str = 'b3d8f1a6c925'
down_revision: Union[str, Sequence[str], None] = 'b82c3fbf011a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SQL = r"""
UPDATE gpu_title_extractions SET chipset = 'RX 9060 XT', status = 'ok', error = NULL,
       notes = 'chip set by hand from the title (was RX 9000), owner review 2026-10-08'
WHERE product_id = 6045 AND chipset = 'RX 9000';
"""


def upgrade() -> None:
    op.execute(SQL)
    from matching.gpu_rekey import rekey_gpus

    session = Session(bind=op.get_bind())
    stats = rekey_gpus(session, dry_run=False)
    session.flush()
    print(f"[gpu_rx9000_key_fix] {stats}")


def downgrade() -> None:
    pass
