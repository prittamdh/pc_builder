"""re-key CPU listings: brand + model number, series dropped

Revision ID: b2d8f6a1c043
Revises: a1c7e5f90b32
Create Date: 2026-10-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session

revision: str = 'b2d8f6a1c043'
down_revision: Union[str, Sequence[str], None] = 'a1c7e5f90b32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The series in the key split CPUs whenever the LLM mislabelled it (a 9700X as
    "Ryzen 9") or the brand came back unknown. See matching/cpu_identity.py. Simulated
    on live data 2026-10-02: 108 models -> 103, five real splits joined, no new merges."""
    from matching.rekey import rekey_cpus

    session = Session(bind=op.get_bind())
    stats = rekey_cpus(session, dry_run=False)
    session.flush()
    print(f"[rekey_cpu_identity] {stats}")


def downgrade() -> None:
    # The old keys split real CPUs; there is nothing correct to go back to.
    pass
