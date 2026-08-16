"""Guards on CompatibilityEngine.filter_candidates.

The failure this covers was silent: _resolve_slot returned [] for a slot with no
spec resolver, filter_candidates zipped that against the candidate list, and the
zip truncated to zero - so every candidate was dropped and the picker showed an
empty list with no error anywhere.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from services.compatibility_engine import CompatibilityEngine


class _FakeProduct:
    def __init__(self, pid, p_category, canonical_id=None):
        self.id = pid
        self.p_category = p_category
        self.canonical_id = canonical_id
        self.name = f"product-{pid}"


class TestResolveSlotContract:
    """_resolve_slot must return exactly one view per product, for every slot."""

    def test_unknown_slot_returns_one_view_per_product(self):
        engine = CompatibilityEngine(session=None)
        products = [_FakeProduct(1, "Monitor"), _FakeProduct(2, "Monitor")]
        resolved = engine._resolve_slot("monitor", products)
        assert len(resolved) == len(products)

    def test_empty_product_list_returns_empty(self):
        engine = CompatibilityEngine(session=None)
        assert engine._resolve_slot("monitor", []) == []


class TestFilterCandidatesFallback:
    def test_slot_without_rules_keeps_all_candidates(self, monkeypatch):
        """A monitor has no compatibility rules, so nothing may be filtered out."""
        engine = CompatibilityEngine(session=None)
        candidates = [_FakeProduct(10, "Monitor"), _FakeProduct(11, "Monitor")]

        # Pretend a CPU is already selected, so the "nothing selected" early return
        # doesn't hide the behaviour under test.
        monkeypatch.setattr(
            engine, "_group_selections",
            lambda ids: {"cpu": [SimpleNamespace(socket="AM5", tdp=105)]},
        )

        kept = engine.filter_candidates("monitor", [1], candidates)
        assert len(kept) == len(candidates)

    def test_nothing_selected_returns_candidates_untouched(self, monkeypatch):
        engine = CompatibilityEngine(session=None)
        candidates = [_FakeProduct(10, "GPU")]
        monkeypatch.setattr(engine, "_group_selections", lambda ids: {})
        assert engine.filter_candidates("gpu", [], candidates) == candidates
