"""
Test-first for scripts/clear_ungrounded_psu_tiers.py's pure logic: which rows it
clears, the reversible notes entry it writes, and what reconciliation would re-fill
afterwards.

Owner ruling 2026-09-25 ("absent beats wrong"): clear the stored 80 PLUS tier on the
PSU title extractions the grounding audit puts in bucket a) cybenetics_leak and
b) no_tier_wording. The trap: reconcile_group_trims() fills a silent listing from
siblings that agree on one trim, so a cleared row must only be re-filled from a sibling
whose own tier survives the clear - never from another row being cleared.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import clear_ungrounded_psu_tiers as clear  # noqa: E402


@dataclass
class _Row:
    product_id: int
    raw_title: str
    efficiency_rating: str | None
    brand: str = "Brand"
    model_number: str = "M1"
    wattage: int = 650
    status: str = "ok"
    notes: str | None = None
    llm_model: str | None = "ministral-14b-latest"
    id: int = 0


def test_selects_exactly_the_audit_buckets_a_and_b():
    rows = [
        _Row(1, "CORSAIR RM850e Cybenetics Gold Modular 850W Power Supply", "80+ Gold"),   # a)
        _Row(2, "Ant Esports FG650 V2 650 Watt Fully Modular SMPS", "gold"),              # b)
        _Row(3, "Ant Esports FG650 V2 650W 80 Plus Gold SMPS", "80+ Gold"),               # grounded
        _Row(4, "Asus ROG Strix 750W Gold SMPS", "80+ Gold"),                             # bare word, owner rule
        _Row(5, "Circle Raw Power 650W SMPS", None),                                      # untiered
        _Row(6, "MSI MAG A850GL PCIE5 White Gold ATX 3.1 SMPS", "80+ White"),             # other_ungrounded
    ]
    plan = clear.plan_clear(rows)
    assert [(r.product_id, bucket) for r, bucket in plan] == [
        (1, "cybenetics_leak"), (2, "no_tier_wording"),
    ]


def test_extra_ids_are_opt_in_and_labelled():
    """Rows outside a)/b) are only ever cleared when named explicitly (an owner call),
    and carry their own reason label."""
    rows = [
        _Row(6, "MSI MAG A850GL PCIE5 White Gold ATX 3.1 SMPS", "80+ White"),
        _Row(7, "Ant Esports FG650 V2 650W 80 Plus Gold SMPS", "80+ Gold"),
    ]
    assert clear.plan_clear(rows) == []
    plan = clear.plan_clear(rows, extra_ids={6})
    assert [(r.product_id, bucket) for r, bucket in plan] == [(6, "extra_id")]
    # An extra id with no stored tier has nothing to clear.
    assert clear.plan_clear([_Row(8, "X 650W", None)], extra_ids={8}) == []


def test_note_records_old_value_reason_and_date_and_keeps_history():
    note = clear.clearing_note(None, "80+ Gold", "cybenetics_leak", "2026-09-25")
    assert "2026-09-25" in note and "'80+ Gold'" in note and "cybenetics" in note.lower()
    assert note.startswith(clear.NOTE_PREFIX)

    kept = clear.clearing_note("manual correction 2026-09-24: audit_psu_trim_conflicts",
                               "gold", "no_tier_wording", "2026-09-25")
    first, second = kept.split("\n")
    assert first == "manual correction 2026-09-24: audit_psu_trim_conflicts"
    assert second.startswith(clear.NOTE_PREFIX) and "'gold'" in second


def test_old_value_is_recoverable_from_the_note():
    note = clear.clearing_note("earlier", "80+ Platinum", "no_tier_wording", "2026-09-25")
    assert clear.old_value_from_notes(note) == "80+ Platinum"
    assert clear.old_value_from_notes("nothing here") is None


def test_sibling_being_cleared_never_refills():
    """Antec Atom V550 V2: every tiered listing is itself ungrounded (Bronze and Gold
    both from no title wording). Cleared together, nothing is left to propagate."""
    rows = [
        _Row(1, "Antec Atom V550 V2 SMPS", "bronze"),
        _Row(2, "Antec Atom V550 V2 550 Watt Power Supply", "bronze"),
        _Row(3, "Antec Atom V550 V2 Non-Modular 550 watt PSU", "80+ Gold"),
    ]
    cleared = {r.product_id for r, _ in clear.plan_clear(rows)}
    assert cleared == {1, 2, 3}
    assert clear.refill_preview(rows, cleared) == {1: None, 2: None, 3: None}


def test_grounded_sibling_refills():
    rows = [
        _Row(1, "Ant Esports FG650 V2 650 Watt Fully Modular SMPS", "gold"),
        _Row(2, "Ant Esports FG650 V2 650W 80 Plus Gold SMPS", "80+ Gold"),
    ]
    cleared = {r.product_id for r, _ in clear.plan_clear(rows)}
    assert clear.refill_preview(rows, cleared) == {1: "gold"}


def test_refill_follows_the_grounded_sibling_not_the_cleared_value():
    """Corsair AX1600i: the ungrounded row said Gold; the grounded sibling says
    Titanium. After the clear the row takes Titanium."""
    rows = [
        _Row(1, "Corsair AX1600i 1600 Watt Digital ATX Fully Modular", "80+ Gold"),
        _Row(2, "CORSAIR AX1600i 1600W 80+ Titanium Fully Modular", "80+ Titanium"),
    ]
    assert clear.refill_preview(rows, {1}) == {1: "titanium"}


def test_refill_ignores_rows_reconciliation_does_not_read():
    """reconcile_group_trims only reads status='ok' rows, so the preview must too."""
    rows = [
        _Row(1, "Brand M1 650W SMPS", "gold"),
        _Row(2, "Brand M1 650W 80 Plus Gold", "80+ Gold", status="needs_review"),
    ]
    assert clear.refill_preview(rows, {1}) == {1: None}


def test_multi_trim_group_is_flagged_not_filled():
    rows = [
        _Row(1, "ASUS TUF Gaming 750W SMPS", "gold"),
        _Row(2, "ASUS TUF Gaming 750W 80+ Bronze", "80+ Bronze"),
        _Row(3, "ASUS TUF Gaming 750W 80+ Gold", "80+ Gold"),
    ]
    assert clear.refill_preview(rows, {1}) == {1: "needs_review"}
