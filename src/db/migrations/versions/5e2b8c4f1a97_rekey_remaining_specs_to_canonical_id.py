"""rekey gpu/motherboard/ram/psu/cabinet/cooler/ssd specs to canonical_id

Revision ID: 5e2b8c4f1a97
Revises: 3f7c9e2a8d16
Create Date: 2026-08-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '5e2b8c4f1a97'
down_revision: Union[str, Sequence[str], None] = '3f7c9e2a8d16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["gpu_specs", "motherboard_specs", "ram_specs", "psu_specs", "cabinet_specs", "cooler_specs", "ssd_specs"]


def upgrade() -> None:
    """Re-key from product_id (per-listing) to canonical_id (per unique real-world
    model), matching the cpu_specs/monitor_specs pattern established earlier - these
    tables previously held one row per listing, populated by the superseded regex
    normalizer, and are now meant to hold one row per real product model, populated
    by the LLM Mistral+Claude cross-verification pipeline. Existing rows are wiped
    since the grain is changing (a per-listing row has no meaning once keyed by
    canonical_id) and the prior data was already deprioritized in favor of
    *_title_extractions in CompatibilityEngine._merge()."""
    for table in TABLES:
        op.execute(f"DELETE FROM {table}")
        op.drop_constraint(f"{table}_product_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "product_id")
        op.alter_column(table, "canonical_id", existing_type=sa.String(length=255), nullable=False)
        op.create_unique_constraint(f"uq_{table}_canonical_id", table, ["canonical_id"])
        op.add_column(table, sa.Column("brand", sa.String(length=50), nullable=True))
        op.add_column(table, sa.Column("confidence", sa.String(length=20), nullable=True))
        op.add_column(table, sa.Column("notes", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("llm_model", sa.String(length=100), nullable=True))
        op.add_column(table, sa.Column("raw_response", postgresql.JSONB(), nullable=True))
        op.add_column(table, sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"))
        op.add_column(table, sa.Column("error", sa.Text(), nullable=True))
        op.create_index(f"ix_{table}_brand", table, ["brand"])
        op.create_index(f"ix_{table}_status", table, ["status"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_status", table_name=table, if_exists=True)
        op.drop_index(f"ix_{table}_brand", table_name=table, if_exists=True)
        op.drop_column(table, "error")
        op.drop_column(table, "status")
        op.drop_column(table, "raw_response")
        op.drop_column(table, "llm_model")
        op.drop_column(table, "notes")
        op.drop_column(table, "confidence")
        op.drop_column(table, "brand")
        op.drop_constraint(f"uq_{table}_canonical_id", table, type_="unique")
        op.alter_column(table, "canonical_id", existing_type=sa.String(length=255), nullable=True)
        op.add_column(table, sa.Column("product_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"{table}_product_id_fkey", table, "products", ["product_id"], ["id"], ondelete="CASCADE")
