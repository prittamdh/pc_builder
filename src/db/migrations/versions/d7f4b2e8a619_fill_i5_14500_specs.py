"""fill the Intel Core i5-14500's specs

Revision ID: d7f4b2e8a619
Revises: c3e1a9d7b552
Create Date: 2026-10-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd7f4b2e8a619'
down_revision: Union[str, Sequence[str], None] = 'c3e1a9d7b552'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The only CPU of 91 with no cores, threads or TDP (review of 2026-10-05). Values from
# Intel's specification page (ark, SKU 236784), supplied by the owner: 6P + 8E cores,
# 2.6 GHz P-core base, 5.0 GHz max turbo, 65 W base power, UHD Graphics 770.
SPECS = dict(socket="LGA1700", cores=14, threads=20, base_clock=2.6, boost_clock=5.0,
             tdp=65, integrated_graphics=True, architecture="Raptor Lake Refresh")
NOTE = "Filled by hand from intel.com ark SKU 236784 (2026-10-06)."


def upgrade() -> None:
    bind = op.get_bind()
    cid = bind.execute(sa.text(
        "SELECT canonical_id FROM canonical_parts WHERE category = 'cpu' AND canonical_id = 'cpu:intel:14500'"
    )).scalar()
    if cid is None:
        print("[fill_i5_14500_specs] no cpu:intel:14500 model; nothing to fill")
        return
    params = {**SPECS, "cid": cid, "note": NOTE}
    exists = bind.execute(sa.text("SELECT 1 FROM cpu_specs WHERE canonical_id = :cid"), params).scalar()
    if exists:
        bind.execute(sa.text("""
            UPDATE cpu_specs SET socket = :socket, cores = :cores, threads = :threads,
                base_clock = :base_clock, boost_clock = :boost_clock, tdp = :tdp,
                integrated_graphics = :integrated_graphics, architecture = :architecture,
                notes = :note, status = 'ok'
            WHERE canonical_id = :cid"""), params)
    else:
        bind.execute(sa.text("""
            INSERT INTO cpu_specs (canonical_id, socket, cores, threads, base_clock, boost_clock,
                tdp, integrated_graphics, architecture, notes, status)
            VALUES (:cid, :socket, :cores, :threads, :base_clock, :boost_clock, :tdp,
                :integrated_graphics, :architecture, :note, 'ok')"""), params)
    print("[fill_i5_14500_specs] filled", cid)


def downgrade() -> None:
    pass
