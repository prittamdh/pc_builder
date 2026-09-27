"""After the re-key, no GPU model mixes listings of different memory sizes, and no
"9060XT"-style spelling splits a card from its twin. Reads the live database."""
from collections import defaultdict

import pytest
from sqlalchemy import select

from matching.gpu_identity import memory_gb_from_title


@pytest.fixture(scope="module")
def gpu_listings():
    from db.session import SessionLocal
    from db.models.product import Product

    with SessionLocal() as s:
        rows = s.execute(
            select(Product.canonical_id, Product.name)
            .where(Product.p_category == "GPU", Product.canonical_id.is_not(None))
        ).all()
    if not rows:
        pytest.skip("no GPU listings in this database")
    return rows


def test_no_model_mixes_memory_sizes(gpu_listings):
    sizes = defaultdict(set)
    for cid, name in gpu_listings:
        gb = memory_gb_from_title(name)
        if gb:
            sizes[cid].add(gb)
    mixed = {cid: s for cid, s in sizes.items() if len(s) > 1}
    assert not mixed, f"{len(mixed)} models mix memory sizes, e.g. {list(mixed.items())[:5]}"


def test_no_glued_chipset_spellings(gpu_listings):
    glued = {cid for cid, _ in gpu_listings if any(t in cid for t in ("0xt", "0ti", "0xtx"))}
    assert not glued, sorted(glued)[:10]
