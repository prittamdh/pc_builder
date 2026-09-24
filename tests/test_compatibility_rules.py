from services.compatibility_rules import RULES


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
