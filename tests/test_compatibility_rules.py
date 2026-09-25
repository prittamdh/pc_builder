import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from domain.builder import BuildSummary, CompatibilityWarning  # noqa: E402
from services.compatibility_engine import CompatibilityEngine  # noqa: E402
from services.compatibility_rules import RULES, FIELD_LABELS, rule_applies  # noqa: E402


def test_no_rule_compares_radiator_size_with_cooler_height():
    """A 360mm AIO radiator is not a 360mm-tall tower; comparing them warned on every AIO."""
    assert not any(
        r.field_a == "radiator_size_mm" and r.field_b == "max_cooler_height_mm" for r in RULES
    )


def test_gpu_clearance_rule_still_present():
    assert any(r.field_a == "length_mm" and r.field_b == "max_gpu_length_mm" for r in RULES)


def test_cooler_height_rule_uses_the_coolers_own_height():
    rule = next(r for r in RULES if r.field_b == "max_cooler_height_mm")
    assert (rule.slot_a, rule.field_a, rule.op, rule.level) == ("cooler", "height_mm", "le", "error")


def test_radiator_rule_is_aio_only_and_a_warning():
    rule = next(r for r in RULES if r.field_b == "max_radiator_mm")
    assert (rule.slot_a, rule.field_a, rule.op, rule.level) == ("cooler", "aio_radiator_mm", "le", "warning")


# ---------------------------------------------------------------------------
# FIT-01 / FIT-02: a missing spec is "unverified", never a silent pass.
# The engine is driven with SimpleNamespace views (the same approach as
# tests/test_compatibility_filtering.py), so no database is touched.
# ---------------------------------------------------------------------------

# One passing value for every field any rule reads, per slot.
_GOOD = {
    "cpu": {"socket": "AM5", "tdp": 105},
    "motherboard": {"socket": "AM5", "memory_type": "DDR5", "memory_slots": 4,
                    "max_memory_gb": 128, "form_factor": "ATX"},
    "ram": {"memory_type": "DDR5", "modules": 2, "capacity_gb": 32},
    "cooler": {"supported_sockets": "AM4, AM5, LGA1700", "height_mm": 155,
               "cooler_type": "Air", "aio_radiator_mm": None},
    "gpu": {"length_mm": 300, "tdp": 200, "recommended_psu": None},
    "case": {"max_gpu_length_mm": 360, "max_cooler_height_mm": 165,
             "max_radiator_mm": 360, "form_factor": "ATX"},
    "psu": {"wattage": 850},
}
_AIO = {"supported_sockets": "AM4, AM5, LGA1700", "height_mm": None,
        "cooler_type": "AIO Liquid", "aio_radiator_mm": 240}


def _view(slot, name=None, **overrides):
    base = dict(_AIO if overrides.pop("_aio", False) else _GOOD[slot])
    base.update(overrides)
    return SimpleNamespace(product_name=name or f"Test {slot.upper()}", **base)


def _run(monkeypatch, selections):
    engine = CompatibilityEngine(session=None)
    monkeypatch.setattr(engine, "_group_selections", lambda ids: selections)
    compatible, warnings, wattage = engine.validate_build([1, 2])
    return BuildSummary(compatible=compatible, warnings=warnings, estimated_wattage=wattage,
                        total_min_cost=Decimal("0"), store_breakdown=[])


def _levels(summary, level):
    return [w for w in summary.warnings if w.level == level]


def _rule_cases():
    for i, rule in enumerate(RULES):
        for side in ("a", "b"):
            yield pytest.param(
                i, side,
                id=f"{i}-{rule.slot_a}.{rule.field_a}-{rule.slot_b}.{rule.field_b}-missing-{side}")


def test_field_labels_cover_every_rule_field():
    for rule in RULES:
        assert rule.field_a in FIELD_LABELS and rule.field_b in FIELD_LABELS


@pytest.mark.parametrize("rule_index,side", list(_rule_cases()))
def test_each_rule_reports_unverified_when_a_value_is_missing(monkeypatch, rule_index, side):
    rule = RULES[rule_index]
    aio = rule.field_a == "aio_radiator_mm"  # the radiator rule only applies to AIOs
    missing_slot, missing_field = (
        (rule.slot_a, rule.field_a) if side == "a" else (rule.slot_b, rule.field_b))
    views = {
        rule.slot_a: _view(rule.slot_a, _aio=aio and rule.slot_a == "cooler"),
        rule.slot_b: _view(rule.slot_b),
    }
    setattr(views[missing_slot], missing_field, None)
    views[missing_slot].product_name = "Missing-Data Part"

    summary = _run(monkeypatch, {k: [v] for k, v in views.items()})

    unverified = _levels(summary, "unverified")
    assert len(unverified) == 1, summary.warnings
    msg = unverified[0].message
    assert "Missing-Data Part" in msg
    assert FIELD_LABELS[missing_field] in msg
    assert summary.compatible is True
    assert summary.verdict == "No problems found - 1 check unverified"


def test_every_rule_has_an_unverified_case():
    covered = {p.values[0] for p in _rule_cases()}
    assert covered == set(range(len(RULES)))


def test_case_without_gpu_clearance_is_unverified_not_passed(monkeypatch):
    """ROADMAP Phase 1 Success Criterion 1."""
    summary = _run(monkeypatch, {
        "gpu": [_view("gpu", "Test GPU", length_mm=300)],
        "case": [_view("case", "Test Case", max_gpu_length_mm=None)],
    })
    unverified = _levels(summary, "unverified")
    assert len(unverified) == 1
    assert "Test Case" in unverified[0].message
    assert "GPU clearance" in unverified[0].message
    assert summary.unverified_count == 1
    assert summary.verdict == "No problems found - 1 check unverified"


def test_unverified_when_both_values_missing_names_both_parts(monkeypatch):
    summary = _run(monkeypatch, {
        "gpu": [_view("gpu", "Test GPU", length_mm=None)],
        "case": [_view("case", "Test Case", max_gpu_length_mm=None)],
    })
    unverified = _levels(summary, "unverified")
    assert len(unverified) == 1
    assert "Test GPU" in unverified[0].message and "Test Case" in unverified[0].message


def test_one_slot_empty_gives_no_item(monkeypatch):
    summary = _run(monkeypatch, {"gpu": [_view("gpu", length_mm=None)]})
    assert _levels(summary, "unverified") == []
    assert summary.verdict == "All checks passed"


def test_unrecognised_form_factor_is_unverified_not_passed(monkeypatch):
    """form_factor_fits used to pass silently when a value could not be parsed."""
    summary = _run(monkeypatch, {
        "motherboard": [_view("motherboard", "Odd Board")],
        "case": [_view("case", "Odd Case", form_factor="Mid Tower")],
    })
    unverified = _levels(summary, "unverified")
    assert len(unverified) == 1
    assert "Odd Case" in unverified[0].message and "form factor" in unverified[0].message


def test_blank_string_counts_as_missing(monkeypatch):
    summary = _run(monkeypatch, {
        "cpu": [_view("cpu", "Test CPU")],
        "cooler": [_view("cooler", "Blank Cooler", supported_sockets="  ")],
    })
    assert len(_levels(summary, "unverified")) == 1
    assert _levels(summary, "warning") == []


def test_part_names_are_stored_unmodified(monkeypatch):
    """Escaping is the renderer's job; the API carries the stored name as-is."""
    name = 'Evil <img src=x onerror=alert(1)> "Case" & Co'
    summary = _run(monkeypatch, {
        "gpu": [_view("gpu")],
        "case": [_view("case", name, max_gpu_length_mm=None)],
    })
    assert name in _levels(summary, "unverified")[0].message


class TestRuleApplies:
    """Pitfall 8: a None that means 'does not apply' is not missing data."""

    def test_air_cooler_skips_the_radiator_check(self, monkeypatch):
        summary = _run(monkeypatch, {
            "cooler": [_view("cooler", "Air Cooler", cooler_type="Air", aio_radiator_mm=None)],
            "case": [_view("case", max_radiator_mm=360)],
        })
        assert summary.warnings == []
        assert summary.verdict == "All checks passed"

    def test_aio_skips_the_cooler_height_check(self, monkeypatch):
        summary = _run(monkeypatch, {
            "cooler": [_view("cooler", "Test AIO", _aio=True)],
            "case": [_view("case")],
        })
        assert summary.warnings == []

    def test_unknown_cooler_type_is_unverified_for_both(self, monkeypatch):
        summary = _run(monkeypatch, {
            "cooler": [_view("cooler", "Mystery Cooler", cooler_type=None, height_mm=None,
                             aio_radiator_mm=None)],
            "case": [_view("case")],
        })
        msgs = [w.message for w in _levels(summary, "unverified")]
        assert len(msgs) == 2
        assert any(FIELD_LABELS["height_mm"] in m for m in msgs)
        assert any(FIELD_LABELS["aio_radiator_mm"] in m for m in msgs)

    def test_rule_applies_directly(self):
        height = next(r for r in RULES if r.field_a == "height_mm")
        radiator = next(r for r in RULES if r.field_a == "aio_radiator_mm")
        air, aio, unknown = (SimpleNamespace(cooler_type=t) for t in ("Air", "AIO 360", None))
        case = SimpleNamespace()
        assert rule_applies(height, air, case) and not rule_applies(height, aio, case)
        assert rule_applies(radiator, aio, case) and not rule_applies(radiator, air, case)
        assert rule_applies(height, unknown, case) and rule_applies(radiator, unknown, case)


class TestClearanceAdjacency:
    def test_equal_length_fits(self, monkeypatch):
        summary = _run(monkeypatch, {"gpu": [_view("gpu", length_mm=360)],
                                     "case": [_view("case", max_gpu_length_mm=360)]})
        assert summary.warnings == [] and summary.compatible

    def test_one_mm_over_is_an_error(self, monkeypatch):
        summary = _run(monkeypatch, {"gpu": [_view("gpu", length_mm=361)],
                                     "case": [_view("case", max_gpu_length_mm=360)]})
        assert [w.level for w in summary.warnings] == ["error"]
        assert "GPU Clearance Error" in summary.warnings[0].message
        assert summary.compatible is False
        assert summary.verdict == "Problems found"


def _summary_of(levels):
    return BuildSummary(compatible="error" not in levels,
                        warnings=[CompatibilityWarning(level=lv, message=lv) for lv in levels],
                        estimated_wattage=0, total_min_cost=Decimal("0"), store_breakdown=[])


class TestVerdict:
    @pytest.mark.parametrize("levels,expected", [
        ([], "All checks passed"),
        (["unverified"], "No problems found - 1 check unverified"),
        (["unverified", "unverified"], "No problems found - 2 checks unverified"),
        (["error", "unverified", "unverified", "unverified"], "Problems found"),
        (["unverified", "unverified", "unverified", "error"], "Problems found"),
        (["warning"], "Problems found"),
        (["unverified", "warning"], "Problems found"),
    ])
    def test_verdict_strings(self, levels, expected):
        assert _summary_of(levels).verdict == expected

    def test_never_all_passed_while_unverified(self):
        for n in range(1, 5):
            s = _summary_of(["unverified"] * n)
            assert s.unverified_count == n
            assert s.verdict != "All checks passed"

    def test_verdict_is_serialized(self):
        dumped = _summary_of(["unverified"]).model_dump(mode="json")
        assert dumped["verdict"] == "No problems found - 1 check unverified"
        assert dumped["unverified_count"] == 1
        assert dumped["wattage_notes"] == []

    def test_empty_build_is_all_checks_passed(self):
        engine = CompatibilityEngine(session=None)
        compatible, warnings, wattage = engine.validate_build([])
        s = BuildSummary(compatible=compatible, warnings=warnings, estimated_wattage=wattage,
                         total_min_cost=Decimal("0"), store_breakdown=[])
        assert s.verdict == "All checks passed" and s.unverified_count == 0


def test_warnings_are_deterministic(monkeypatch):
    sel = {
        "cpu": [_view("cpu", socket=None)],
        "motherboard": [_view("motherboard", memory_slots=None)],
        "ram": [_view("ram")],
        "gpu": [_view("gpu")],
        "case": [_view("case", max_gpu_length_mm=None)],
    }
    first = _run(monkeypatch, sel).warnings
    second = _run(monkeypatch, sel).warnings
    assert first == second
    # RULES order: CPU/board socket (rule 0), RAM slots (rule 2), GPU clearance (rule 5).
    msgs = [w.message for w in first if w.level == "unverified"]
    assert len(msgs) == 3, msgs
    assert FIELD_LABELS["socket"] in msgs[0]
    assert FIELD_LABELS["memory_slots"] in msgs[1]
    assert FIELD_LABELS["max_gpu_length_mm"] in msgs[2]


class TestFilterCandidatesKeepsUnknowns:
    def test_candidate_with_missing_value_is_still_offered(self, monkeypatch):
        class _P:
            def __init__(self, pid):
                self.id, self.p_category, self.canonical_id = pid, "Cabinet", None
                self.name = f"case-{pid}"

        engine = CompatibilityEngine(session=None)
        monkeypatch.setattr(engine, "_group_selections",
                            lambda ids: {"gpu": [_view("gpu", length_mm=300)]})
        monkeypatch.setattr(engine, "_resolve_slot", lambda slot, prods: [
            SimpleNamespace(max_gpu_length_mm=None, max_cooler_height_mm=None,
                            max_radiator_mm=None, form_factor=None, product_name=p.name)
            for p in prods])
        candidates = [_P(1), _P(2)]
        assert engine.filter_candidates("case", [9], candidates) == candidates


# ---------------------------------------------------------------------------
# FIT-03: a wattage built on a typical TDP names the part and says "estimate".
# ---------------------------------------------------------------------------
class TestWattageEstimate:
    def test_cpu_without_tdp_is_named_as_an_estimate(self, monkeypatch):
        s = _run(monkeypatch, {"cpu": [_view("cpu", "Mystery CPU", tdp=None)]})
        notes = _levels(s, "estimate")
        assert len(notes) == 1
        msg = notes[0].message
        assert "Mystery CPU" in msg and "120" in msg and "estimate" in msg.lower()
        assert s.wattage_notes == [msg]

    def test_gpu_without_tdp_is_named_as_an_estimate(self, monkeypatch):
        s = _run(monkeypatch, {"gpu": [_view("gpu", "Mystery GPU", tdp=None)]})
        notes = _levels(s, "estimate")
        assert len(notes) == 1
        assert "Mystery GPU" in notes[0].message and "250" in notes[0].message
        assert s.wattage_notes == [notes[0].message]

    def test_known_tdps_give_no_estimate(self, monkeypatch):
        s = _run(monkeypatch, {"cpu": [_view("cpu")], "gpu": [_view("gpu")]})
        assert _levels(s, "estimate") == [] and s.wattage_notes == []

    def test_no_cpu_or_gpu_gives_no_estimate(self, monkeypatch):
        s = _run(monkeypatch, {"ram": [_view("ram")], "motherboard": [_view("motherboard")]})
        assert s.wattage_notes == []

    def test_estimate_does_not_change_the_verdict(self, monkeypatch):
        s = _run(monkeypatch, {"cpu": [_view("cpu", tdp=None)], "gpu": [_view("gpu", tdp=None)]})
        assert len(s.wattage_notes) == 2
        assert s.unverified_count == 0
        assert s.verdict == "All checks passed"

    def test_estimated_wattage_value_is_unchanged(self, monkeypatch):
        s = _run(monkeypatch, {"cpu": [_view("cpu", tdp=None)], "gpu": [_view("gpu", tdp=None)]})
        assert s.estimated_wattage == 120 + 250 + 50
        s = _run(monkeypatch, {"cpu": [_view("cpu", tdp=105)], "gpu": [_view("gpu", tdp=200)]})
        assert s.estimated_wattage == 105 + 200 + 50

    def test_estimate_notes_come_after_psu_capacity_warnings(self, monkeypatch):
        s = _run(monkeypatch, {"cpu": [_view("cpu", tdp=None)], "gpu": [_view("gpu", tdp=None)],
                               "psu": [_view("psu", wattage=450)]})
        levels = [w.level for w in s.warnings]
        assert levels == ["warning", "estimate", "estimate"], s.warnings


# ---------------------------------------------------------------------------
# Fix round 1
# ---------------------------------------------------------------------------
from services.compatibility_rules import cooler_kind, form_factor_index  # noqa: E402


class TestUnknownCoolerType:
    """The extractor stores the literal "Unknown"; it must not read as a known type."""

    @pytest.mark.parametrize("raw,kind", [
        ("AIO Liquid", "aio"), ("aio 240", "aio"), ("Air", "air"), ("AIR tower", "air"),
        ("Unknown", None), ("", None), ("  ", None), (None, None), ("Liquid", None),
    ])
    def test_cooler_kind(self, raw, kind):
        assert cooler_kind(raw) == kind

    def test_rule_applies_treats_unknown_and_blank_as_unknown(self):
        height = next(r for r in RULES if r.field_a == "height_mm")
        radiator = next(r for r in RULES if r.field_a == "aio_radiator_mm")
        case = SimpleNamespace()
        for t in ("Unknown", "", "unknown "):
            cooler = SimpleNamespace(cooler_type=t)
            assert rule_applies(height, cooler, case), t
            assert rule_applies(radiator, cooler, case), t

    def test_unknown_type_reports_height_and_radiator_unverified(self, monkeypatch):
        summary = _run(monkeypatch, {
            "cooler": [_view("cooler", "Mystery Cooler", cooler_type="Unknown", height_mm=None,
                             aio_radiator_mm=None)],
            "case": [_view("case")],
        })
        msgs = [w.message for w in _levels(summary, "unverified")]
        assert len(msgs) == 2, summary.warnings
        assert any(FIELD_LABELS["height_mm"] in m for m in msgs)
        assert any(FIELD_LABELS["aio_radiator_mm"] in m for m in msgs)
        assert summary.verdict == "No problems found - 2 checks unverified"


class _FakeSession:
    """Answers _resolve_slot's two queries from in-memory rows, keyed by model class."""

    def __init__(self, rows_by_model):
        self.rows_by_model = rows_by_model

    def scalars(self, stmt):
        model = stmt.column_descriptions[0]["entity"]
        return list(self.rows_by_model.get(model, []))


class TestCoolerResolve:
    def _resolve(self, ext_type, spec_type, size=240):
        from db.models.category_specs import CoolerSpecs
        from db.models.cooler_title_extraction import CoolerTitleExtraction
        product = SimpleNamespace(id=1, canonical_id="c-1", name="Some Cooler")
        spec = SimpleNamespace(canonical_id="c-1", cooler_type=spec_type, radiator_size_mm=size,
                               supported_sockets=None, tdp_rating=None, height_mm=None)
        ext = SimpleNamespace(product_id=1, cooler_type=ext_type, size_mm=None)
        engine = CompatibilityEngine(session=_FakeSession({CoolerSpecs: [spec],
                                                           CoolerTitleExtraction: [ext]}))
        return engine._resolve_slot("cooler", [product])[0]

    @pytest.mark.parametrize("placeholder", ["Unknown", "", "  "])
    def test_specs_type_wins_over_an_unknown_extraction(self, placeholder):
        view = self._resolve(placeholder, "AIO Liquid")
        assert view.cooler_type == "AIO Liquid"
        assert view.aio_radiator_mm == 240

    def test_unknown_everywhere_resolves_to_none(self):
        view = self._resolve("Unknown", None)
        assert view.cooler_type is None
        assert view.aio_radiator_mm is None

    def test_known_extraction_still_wins(self):
        assert self._resolve("Air", "AIO Liquid").cooler_type == "Air"


class TestFormFactorIndex:
    # Every distinct value in motherboard_specs / motherboard_title_extractions /
    # cabinet_specs / cabinet_title_extractions (read-only query, 2026-09-25):
    # MATX, ATX, EATX, ITX, CEB, EEB, NULL - plus the spellings titles use.
    @pytest.mark.parametrize("value,expected", [
        ("ITX", 0), ("MATX", 1), ("ATX", 2), ("EATX", 3),
        ("CEB", None), ("EEB", None), (None, None), ("", None),
        ("E-ATX", 3), ("E ATX", 3), ("Extended ATX", 3), ("eatx", 3),
        ("Micro-ATX", 1), ("Micro ATX", 1), ("microATX", 1), ("mATX", 1), ("M-ATX", 1),
        ("Mini-ITX", 0), ("Mini ITX", 0), ("mini-itx", 0),
        ("ATX Mid Tower", 2), ("Mid Tower", None), ("XL-ATX", None),
        # A case listing several sizes fits the largest of them.
        ("ATX/Micro-ATX/Mini-ITX", 2), ("E-ATX / ATX", 3),
    ])
    def test_values(self, value, expected):
        assert form_factor_index(value) == expected

    def test_eatx_board_in_atx_case_is_a_problem(self, monkeypatch):
        summary = _run(monkeypatch, {
            "motherboard": [_view("motherboard", form_factor="EATX")],
            "case": [_view("case", form_factor="ATX")],
        })
        assert [w.level for w in summary.warnings] == ["error"]
        assert summary.verdict == "Problems found"

    def test_micro_atx_board_fits_an_atx_case(self, monkeypatch):
        summary = _run(monkeypatch, {
            "motherboard": [_view("motherboard", form_factor="Micro-ATX")],
            "case": [_view("case", form_factor="ATX")],
        })
        assert summary.warnings == [] and summary.verdict == "All checks passed"


class TestPsuWattageUnknown:
    @pytest.mark.parametrize("wattage", [None, 0])
    @pytest.mark.parametrize("other", ["cpu", "gpu"])
    def test_psu_without_wattage_is_unverified(self, monkeypatch, wattage, other):
        summary = _run(monkeypatch, {
            other: [_view(other)],
            "psu": [_view("psu", "Mystery PSU", wattage=wattage)],
        })
        items = _levels(summary, "unverified")
        assert len(items) == 1, summary.warnings
        assert "Mystery PSU" in items[0].message and "wattage" in items[0].message
        assert summary.verdict != "All checks passed"

    def test_psu_alone_is_not_checked(self, monkeypatch):
        summary = _run(monkeypatch, {"psu": [_view("psu", wattage=None)]})
        assert summary.warnings == []

    def test_psu_with_wattage_gives_no_item(self, monkeypatch):
        summary = _run(monkeypatch, {"cpu": [_view("cpu")], "psu": [_view("psu", wattage=850)]})
        assert summary.warnings == []

    def test_unverified_psu_comes_before_estimates(self, monkeypatch):
        summary = _run(monkeypatch, {"cpu": [_view("cpu", tdp=None)],
                                     "psu": [_view("psu", wattage=None)]})
        assert [w.level for w in summary.warnings] == ["unverified", "estimate"]
