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


def test_classify_row_buckets_other_ungrounded_when_tier_word_present_but_not_near_80():
    """Tier word present in the title as ordinary text, unrelated to any 80 PLUS or
    Cybenetics wording and no manufacturer rule - still ungrounded, but not the
    Cybenetics leak or the pure-recall case, so it gets its own bucket rather than
    being miscounted into either."""
    title = "Ant Esports Gold Series Cabinet Fan Pack (Not a Real PSU Title) 650W SMPS"
    assert audit.classify_row(title, "80+ Gold") == "other_ungrounded"
