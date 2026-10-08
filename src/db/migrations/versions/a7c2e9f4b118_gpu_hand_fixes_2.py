"""More GPU listings fixed by hand from their titles (owner review 2026-10-08, round 2)

Reference NVIDIA/AMD workstation cards and a few MSI/Zotac GT cards with no brand or
chip. Applied to the local copy of live first.

Revision ID: a7c2e9f4b118
Revises: f1b4d6e2a830
Create Date: 2026-10-08 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session

revision: str = 'a7c2e9f4b118'
down_revision: Union[str, Sequence[str], None] = 'f1b4d6e2a830'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SQL = r"""
-- GPU listings with no brand/chip, read by hand from the title.
UPDATE gpu_title_extractions e SET brand = v.brand, chipset = v.chip, variant = v.variant, status = 'ok', error = NULL,
       notes = 'set by hand from the title, owner review 2026-10-08'
FROM (VALUES
  (19911,'NVIDIA','L40',''),
  (15242,'NVIDIA','RTX PRO 4000 Blackwell',''), (6008,'NVIDIA','RTX PRO 4000 Blackwell',''),
  (16038,'PNY','RTX PRO 4000 Blackwell',''), (16026,'PNY','RTX PRO 4000 Blackwell','SFF'),
  (15225,'NVIDIA','RTX PRO 2000 Blackwell',''),
  (6011,'NVIDIA','RTX PRO 4500 Blackwell',''),
  (6018,'NVIDIA','RTX PRO 5000 Blackwell',''),
  (6026,'NVIDIA','RTX PRO 6000 Blackwell',''), (6025,'NVIDIA','RTX PRO 6000 Blackwell','Max-Q'),
  (6148,'NVIDIA','RTX 4000 Ada',''),
  (16029,'PNY','RTX 5000 Ada',''), (16025,'PNY','RTX 4000 SFF Ada',''),
  (15112,'AMD','Radeon PRO W7700',''), (7528,'AMD','Radeon PRO W7900',''),
  (6095,'MSI','GT 710',''), (6151,'MSI','GT 730',''), (6159,'Zotac','GT 730','LP Zone')
) AS v(pid, brand, chip, variant)
WHERE e.product_id = v.pid;
"""


def upgrade() -> None:
    op.execute(SQL)
    from matching.gpu_rekey import rekey_gpus

    session = Session(bind=op.get_bind())
    stats = rekey_gpus(session, dry_run=False)
    session.flush()
    print(f"[gpu_hand_fixes_2] {stats}")


def downgrade() -> None:
    pass
