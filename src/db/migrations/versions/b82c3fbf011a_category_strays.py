"""Listings in the wrong category moved by hand from their titles (owner review 2026-10-08)

SSDs, a motherboard, a mouse, a PSU tester and CCTV supplies filed under Power Supply;
a monitor, coolers, LCD screens and a racing wheel under Cabinet; a pen drive, a case
fan and loop fittings under CPU Cooler; a Ryzen CPU under Motherboard; DDR5 RAM, an
SSD enclosure and pen drives under Storage. 32 listings. Removable media has no build
slot, so pen drives go to Accessories, not Storage.

The classifier now files these titles the same way (category_named_by_title), so a
re-scrape keeps them where they are put here.

Revision ID: b82c3fbf011a
Revises: a7c2e9f4b118
Create Date: 2026-10-08 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b82c3fbf011a'
down_revision: Union[str, Sequence[str], None] = 'a7c2e9f4b118'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (listing id, category it sits in, category it belongs in). Listing ids are
# production's; the "sits in" check means an id that is something else in another
# database updates nothing.
MOVES = [
    (16760, 'Power Supply', 'Storage'), (16741, 'Power Supply', 'Storage'),
    (20708, 'Power Supply', 'Storage'), (20709, 'Power Supply', 'Storage'),
    (16749, 'Power Supply', 'Motherboard'),
    (16737, 'Power Supply', 'Accessories'), (20710, 'Power Supply', 'Accessories'),
    (17127, 'Power Supply', 'Accessories'), (17128, 'Power Supply', 'Accessories'),
    (20066, 'Power Supply', 'Accessories'), (20067, 'Power Supply', 'Accessories'),
    (20068, 'Power Supply', 'Accessories'), (20069, 'Power Supply', 'Accessories'),
    (16929, 'Cabinet', 'Monitor'),
    (16332, 'Cabinet', 'CPU Cooler'), (17489, 'Cabinet', 'CPU Cooler'),
    (2359, 'Cabinet', 'Accessories'), (20869, 'Cabinet', 'Accessories'),
    (2390, 'Cabinet', 'Accessories'), (2391, 'Cabinet', 'Accessories'),
    (16971, 'Cabinet', 'Accessories'),
    (16454, 'CPU Cooler', 'Accessories'), (21394, 'CPU Cooler', 'Accessories'),
    (16516, 'CPU Cooler', 'Accessories'), (16517, 'CPU Cooler', 'Accessories'),
    (21464, 'CPU Cooler', 'Accessories'),
    (15442, 'Motherboard', 'CPU'),
    (19692, 'Storage', 'RAM'), (17771, 'Storage', 'Accessories'),
    (21251, 'Storage', 'Accessories'), (21252, 'Storage', 'Accessories'),
    (21253, 'Storage', 'Accessories'),
]

# The old category's title extraction is marked so re-keys (status 'ok' only) skip it.
EXTRACTION = {
    'Power Supply': ('psu_title_extractions', 'not_psu'),
    'Cabinet': ('cabinet_title_extractions', 'not_cabinet'),
    'CPU Cooler': ('cooler_title_extractions', 'not_cooler'),
    'Motherboard': ('motherboard_title_extractions', 'not_motherboard'),
    'Storage': ('storage_title_extractions', 'not_storage'),
}


def upgrade() -> None:
    for old in EXTRACTION:
        table, status = EXTRACTION[old]
        moves = [(pid, new) for pid, frm, new in MOVES if frm == old]
        values = ", ".join(f"({pid}, '{new}')" for pid, new in moves)
        op.execute(f"""
            UPDATE {table} e SET status = '{status}', notes = 'not this category, owner review 2026-10-08'
            FROM products p WHERE p.id = e.product_id AND p.p_category = '{old}'
              AND e.product_id IN ({", ".join(str(pid) for pid, _ in moves)})
        """)
        # A new category means a new extraction: back into the queue, like a scrape does.
        op.execute(f"""
            UPDATE products p SET p_category = v.new, canonical_id = NULL, spec_status = 'pending'
            FROM (VALUES {values}) AS v(pid, new)
            WHERE p.id = v.pid AND p.p_category = '{old}'
        """)


def downgrade() -> None:
    # The old categories were wrong; nothing correct to go back to.
    pass
