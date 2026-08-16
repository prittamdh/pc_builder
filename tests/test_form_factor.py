import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from matching.form_factor import normalize_form_factor


class TestSpellingVariants:
    def test_eatx_variants_collapse(self):
        for v in ["E-ATX", "EATX", "e atx", "Extended ATX", "E_ATX"]:
            assert normalize_form_factor(v) == "EATX", v

    def test_matx_variants_collapse(self):
        for v in ["mATX", "MATX", "Micro ATX", "Micro-ATX", "M-ATX", "micro atx"]:
            assert normalize_form_factor(v) == "MATX", v

    def test_itx_variants_collapse(self):
        for v in ["ITX", "Mini-ITX", "Mini ITX", "M-ITX", "mini itx"]:
            assert normalize_form_factor(v) == "ITX", v

    def test_plain_atx(self):
        assert normalize_form_factor("ATX") == "ATX"

    def test_atx_not_swallowed_by_longer_forms(self):
        # "ATX" is a substring of the others; specificity must win.
        assert normalize_form_factor("E-ATX") == "EATX"
        assert normalize_form_factor("Micro ATX") == "MATX"


class TestChassisSizes:
    def test_bare_chassis_size_is_not_a_form_factor(self):
        for v in ["Mid Tower", "Mid-Tower", "Full Tower", "SFF", "Mini Tower"]:
            assert normalize_form_factor(v) is None, v

    def test_chassis_size_falls_back_to_title(self):
        # A case labelled SFF whose title states mATX really is MATX.
        assert normalize_form_factor(
            "SFF", "Lian Li B4-mATX Wood Mesh SFF PC Case Mini"
        ) == "MATX"

    def test_chassis_size_with_uninformative_title_stays_none(self):
        assert normalize_form_factor(
            "Mid-Tower", "CORSAIR FRAME 4000D RS ARGB Mid-Tower PC Case - Black"
        ) is None

    def test_title_stating_atx_is_used(self):
        assert normalize_form_factor(
            "Mid Tower", "Cougar CFV235 Mesh Black ATX Mid Tower Cabinet"
        ) == "ATX"


class TestEdgeCases:
    def test_none_and_empty(self):
        assert normalize_form_factor(None) is None
        assert normalize_form_factor("") is None
        assert normalize_form_factor(None, None) is None

    def test_workstation_ceb_is_eatx_class(self):
        assert normalize_form_factor("CEB") == "EATX"

    def test_unrecognized_returns_none(self):
        assert normalize_form_factor("BTX") is None
