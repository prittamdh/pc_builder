"""
Test-first for scripts/audit_psu_title_tier_grounding.py's pure grounding check.

The benchmark (scripts/benchmark_provider.py) found a second-place provider reporting
"80+ Gold" for a title that states only "Cybenetics Gold" - the prompt's documented
trap (PSU_IDENTITY_BATCH_PROMPT / PSU_SPEC_BATCH_PROMPT in
src/services/groq_extraction_service.py) says to ignore Cybenetics wording entirely
and report the 80 PLUS tier only, treating a tier word inside the MODEL NAME as the
manufacturer's own documented marker (MSI "GL"=Gold/"BN"=Bronze, Super Flower
"Leadex III Gold", Cooler Master "MWE Gold"). These tests lock in what "grounded"
means before the audit script uses it against live data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_psu_title_tier_grounding as audit  # noqa: E402


def test_cybenetics_only_wording_is_ungrounded():
    """Cybenetics-only wording is the exact leak the benchmark found: the tier word is
    on the page, but it names the wrong certification scheme, and the prompt says to
    ignore it entirely - so it must not count as grounding evidence."""
    title = "Corsair RM750E 750W ATX 3.0 Cybenetics Gold Fully Modular Power Supply"
    grounded, reason = audit.is_tier_grounded(title, "80+ Gold")
    assert grounded is False
    # the bucketer must call this out specifically as the Cybenetics leak, not just
    # a generic "ungrounded" result.
    assert audit.classify_row(title, "80+ Gold") == "cybenetics_leak"


def test_80_plus_wording_is_grounded():
    """The straightforward case: the title states the 80 PLUS tier directly."""
    title = "Thermaltake Toughpower GF A3 1050 Watt 80 Plus Gold ATX 3.0 SMPS"
    grounded, reason = audit.is_tier_grounded(title, "80+ Gold")
    assert grounded is True
    assert "80" in reason.lower()


def test_msi_gl_suffix_is_grounded_by_manufacturer_rule():
    """MSI's own "GL" model-name suffix is Gold by the documented manufacturer rule,
    even though the title spells out no 80 PLUS wording at all."""
    title = "MSI MAG A750GL PCIE5 ATX 3.1 Fully Modular SMPS MAG-A750GL-PCIE5"
    grounded, reason = audit.is_tier_grounded(title, "80+ Gold")
    assert grounded is True
    assert "manufacturer" in reason.lower()


def test_msi_bn_suffix_is_grounded_bronze_by_manufacturer_rule():
    title = "MSI MAG A650BN ATX 2.52 Non Modular Power Supply"
    grounded, reason = audit.is_tier_grounded(title, "80+ Bronze")
    assert grounded is True
    assert "manufacturer" in reason.lower()


def test_super_flower_leadex_iii_gold_is_grounded_by_model_name_not_by_80():
    """The prompt's own documented trap case (see the PSU_IDENTITY_BATCH_PROMPT
    few-shot example and PROGRESS.md's 2026-09-20 PSU efficiency section):

        "Super Flower LEADEX III GOLD UP ATX 3.1 750W Cybenetics Platinum
         Certified Gold SMPS Power Supply"

    is 80 PLUS Gold, but the scraped title itself never spells out "80 PLUS" or
    "80+" anywhere - it carries only the Cybenetics wording ("Cybenetics Platinum
    Certified Gold") and the manufacturer's own model name ("LEADEX III GOLD").
    Our call: this is grounded, but ONLY via the documented Super Flower model-name
    rule, never via an "80" marker (there is none in this title) and never via the
    Cybenetics wording (which the prompt says to ignore). A grounding check that
    required "80" wording here would wrongly reject the one case the prompt exists
    to handle correctly; a check that let bare "Cybenetics ... Gold" wording count
    would let the exact leak back in. So the model name is the deciding evidence,
    and the reason string must say so, not "80".
    """
    title = (
        "Super Flower LEADEX III GOLD UP ATX 3.1 750W Cybenetics Platinum "
        "Certified Gold SMPS Power Supply"
    )
    grounded, reason = audit.is_tier_grounded(title, "80+ Gold")
    assert grounded is True
    assert "manufacturer" in reason.lower()
    assert "80" not in reason.lower()


def test_cooler_master_mwe_gold_is_grounded_by_manufacturer_rule():
    title = "Cooler Master MWE Gold 750 V3 ATX 3.0 Fully Modular Power Supply"
    grounded, reason = audit.is_tier_grounded(title, "80+ Gold")
    assert grounded is True
    assert "manufacturer" in reason.lower()


def test_no_tier_wording_at_all_is_ungrounded():
    """A title that states neither an 80 PLUS tier nor any manufacturer-rule marker
    for a tier not literally present anywhere is the "recalled from memory" case."""
    title = "Zebronics ZEB-U550 550W ATX Power Supply"
    grounded, reason = audit.is_tier_grounded(title, "80+ Gold")
    assert grounded is False


def test_80_plus_sign_tight_against_tier_word_is_grounded():
    """Regression: "80+ White" (plus sign immediately followed by the tier word, no
    "PLUS" spelled out) must ground - a naive \\b placed right after the "+" character
    never matches here because "+" and the following space are both non-word
    characters, which silently dropped every "80+ <tier>" title on a first pass."""
    title = "ANT ESPORTS VS500L 500W 80+ White Non Modular ATX 2.0 Power Supply"
    grounded, reason = audit.is_tier_grounded(title, "80+ White")
    assert grounded is True
    assert "80" in reason.lower()


def test_untiered_stored_rating_is_ungrounded():
    """A stored value with no recognisable 80 PLUS tier word grounds nothing."""
    grounded, reason = audit.is_tier_grounded("Some PSU Title", "Certified")
    assert grounded is False


def test_classify_row_buckets_cybenetics_leak():
    title = "Corsair RM750E 750W ATX 3.0 Cybenetics Gold Fully Modular Power Supply"
    assert audit.classify_row(title, "80+ Gold") == "cybenetics_leak"


def test_classify_row_buckets_no_tier_wording():
    title = "Zebronics ZEB-U550 550W ATX Power Supply"
    assert audit.classify_row(title, "80+ Gold") == "no_tier_wording"


def test_classify_row_buckets_grounded():
    title = "Thermaltake Toughpower GF A3 1050 Watt 80 Plus Gold ATX 3.0 SMPS"
    assert audit.classify_row(title, "80+ Gold") == "grounded"


def test_bare_tier_word_is_grounded_by_owner_ruling():
    """Owner decision 2026-09-25: a title that states the tier word without any "80"
    wording ("Asus ROG Strix 750W Gold SMPS") counts as grounded. This used to be the
    residual other_ungrounded bucket (262 live rows)."""
    title = "MSI Mag A850GL PCIE5.1 ATX 3.1 Gold Fully Modular SMPS"
    grounded, reason = audit.is_tier_grounded("Asus ROG Strix 750W Gold SMPS", "80+ Gold")
    assert grounded is True
    assert "2026-09-25" in reason
    assert audit.classify_row(title, "80+ Gold") == "grounded"
    assert audit.classify_row("Deepcool PX1000P 1000W Platinum SMPS", "platinum") == "grounded"


def test_bare_tier_word_rule_does_not_rescue_cybenetics_only_titles():
    """The owner ruling covers bare tier words, not Cybenetics wording: a title whose
    only tier word is "Cybenetics Gold" stays the Cybenetics leak."""
    title = "CORSAIR RM850e Cybenetics Gold Modular 850W Power Supply CP-9020296-IN"
    assert audit.classify_row(title, "80+ Gold") == "cybenetics_leak"
    # A tier word inside a model name next to a Cybenetics token still leaves the
    # title Cybenetics-only (no 80 wording): stays in a), as the audit found it.
    title = "Super Flower Leadex Titanium 2800W ATX 3.1 Cybenetics  Fully Modular PSU"
    assert audit.classify_row(title, "80+ Titanium") == "cybenetics_leak"


def test_tier_word_only_in_cybenetics_phrase_is_not_bare_grounding():
    """80 wording for one tier and "Cybenetics <tier>" for another: the stored
    Cybenetics tier has no grounding, bare or otherwise."""
    title = "Corsair RM750x 80 Plus Bronze ATX PSU Cybenetics Gold"
    assert audit.is_tier_grounded(title, "80+ Gold")[0] is False
    assert audit.classify_row(title, "80+ Gold") == "other_ungrounded"


def test_bare_white_is_a_colour_not_a_tier():
    """The bare-word ruling excludes White: it is far more often the colour. Live row
    20725 stored "80+ White" for an MSI A850GL (GL = Gold) titled "White Gold"."""
    title = "MSI MAG A850GL PCIE5 White Gold ATX 3.1 Fully Modular SMPS"
    assert audit.is_tier_grounded(title, "80+ White")[0] is False
    assert audit.classify_row(title, "80+ White") == "other_ungrounded"


def test_80_marker_names_the_tier_right_after_it_not_a_later_colour():
    """Live row 3993: "80 Plus Platinum White" was stored as "80+ White". The 80
    marker is followed by Platinum; the White after it is the colour."""
    title = ("Gigabyte Aorus Elite P1000W 80 Plus Platinum White Fully Modular "
             "PCIe 5.0 Power Supply GP-AE1000PM PG5 ICE")
    assert audit.is_tier_grounded(title, "80+ White")[0] is False
    assert audit.is_tier_grounded(title, "80+ Platinum")[0] is True
    # Genuine White units stay grounded.
    assert audit.is_tier_grounded(
        "ANT ESPORTS VS500L 500W 80+ White Non Modular ATX 2.0 Power Supply", "80+ White"
    )[0] is True


class _Row:
    """Stand-in for PSUTitleExtraction for the group-level check."""
    def __init__(self, product_id, title, rating, model="M1", status="ok"):
        self.product_id, self.raw_title, self.efficiency_rating = product_id, title, rating
        self.brand, self.model_number, self.wattage, self.status = "Brand", model, 650, status


def test_reconciliation_fill_from_a_grounded_sibling_is_backed():
    """reconcile_group_trims() writes a sibling's trim into a listing whose title is
    silent. Per row that looks like b) no_tier_wording, but the value is grounded in
    the sibling's title - the audit must say so rather than flag it as recalled."""
    rows = [
        _Row(1, "Ant Esports FG650 V2 650 Watt Fully Modular SMPS", "gold"),
        _Row(2, "Ant Esports FG650 V2 650W 80 Plus Gold SMPS", "80+ Gold"),
        _Row(3, "Corsair RM750e Cybenetics Gold SMPS", "gold", model="M2"),
        _Row(4, "Corsair RM750e 750W 80 Plus Gold", "80+ Gold", model="M2"),
    ]
    assert audit.classify_row(rows[0].raw_title, "gold") == "no_tier_wording"
    assert audit.sibling_backed(rows) == {1, 3}


def test_ungrounded_siblings_do_not_back_each_other():
    """Antec Atom V550 V2: every tiered listing is ungrounded, so none backs another."""
    rows = [
        _Row(1, "Antec Atom V550 V2 SMPS", "bronze"),
        _Row(2, "Antec Atom V550 V2 550 Watt Power Supply", "bronze"),
    ]
    assert audit.sibling_backed(rows) == set()


def test_sibling_backing_needs_one_agreed_trim_and_status_ok():
    rows = [
        _Row(1, "ASUS TUF Gaming 750W SMPS", "gold"),
        _Row(2, "ASUS TUF Gaming 750W 80+ Bronze", "80+ Bronze"),
        _Row(3, "ASUS TUF Gaming 750W 80+ Gold", "80+ Gold"),
        _Row(4, "Other X 650W SMPS", "gold", model="M9"),
        _Row(5, "Other X 650W 80 Plus Gold", "80+ Gold", model="M9", status="needs_review"),
        _Row(6, "Brand Z 650W SMPS", "gold", model="M8"),
        _Row(7, "Brand Z 650W 80 Plus Bronze", "80+ Bronze", model="M8"),
    ]
    # 1: grounded siblings disagree; 4: its only grounded sibling is not status ok;
    # 6: the grounded sibling states a different trim.
    assert audit.sibling_backed(rows) == set()
