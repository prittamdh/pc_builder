"""
Unit & Integration Tests for Matching Pipeline Edge Cases.
Tests canonical key building, title formatting variance, near-miss separation, and missing field review flags.
"""
import pytest
from matching.canonical_key_builder import build_canonical_key, make_canonical_key_string


def test_title_formatting_variance_same_key():
    """Verify different title formatting across stores produce the exact same canonical key."""
    title1 = "AMD Ryzen 9 9900X Processor"
    title2 = "RYZEN9-9900X"
    title3 = "AMD 9900X Ryzen 9 CPU"

    key1 = make_canonical_key_string("CPU", build_canonical_key(title1, "CPU"))
    key2 = make_canonical_key_string("CPU", build_canonical_key(title2, "CPU"))
    key3 = make_canonical_key_string("CPU", build_canonical_key(title3, "CPU"))

    assert key1 == key2 == key3 == "cpu:amd:ryzen_9_9900x"


def test_gpu_variant_brand_duplication_regression():
    """Lock in GPU variant brand-duplication fix (no duplicate msi in key)."""
    gpu_title = "MSI GeForce RTX 4070 Ti Super Gaming X Slim 16GB"
    key_dict = build_canonical_key(gpu_title, "GPU")
    key_str = make_canonical_key_string("GPU", key_dict)

    assert key_dict["aib_brand"] == "MSI"
    assert key_dict["variant_model"] == "gaming x"
    assert key_str == "gpu:msi:rtx_4070_ti_super:gaming_x"
    assert "msi:msi" not in key_str


def test_near_miss_different_ram_speed_must_not_match():
    """Verify two RAM kits differing only in speed produce different canonical keys."""
    ram1 = "G.Skill Trident Z5 RGB 32GB (16GBx2) DDR5 6000MHz CL30 RAM"
    ram2 = "G.Skill Trident Z5 RGB 32GB (16GBx2) DDR5 6400MHz CL30 RAM"

    key1 = make_canonical_key_string("RAM", build_canonical_key(ram1, "RAM"))
    key2 = make_canonical_key_string("RAM", build_canonical_key(ram2, "RAM"))

    assert key1 != key2
    assert "6000mhz" in key1
    assert "6400mhz" in key2


def test_missing_critical_field_flags_review():
    """Verify title missing wattage or CL timing flags needs_review gracefully."""
    psu_missing_wattage = "Corsair Power Supply Unit SMPS"
    ram_missing_cl = "Kingston Fury Beast 16GB DDR4 3200MHz Memory"

    key_psu = build_canonical_key(psu_missing_wattage, "PSU")
    key_ram = build_canonical_key(ram_missing_cl, "RAM")

    assert key_psu["wattage"] == "Unknown"
    assert key_ram["cl_timing"] == "Unknown"


def test_cpu_suffix_preservation_distinct_keys():
    """Verify i7-14700 vs i7-14700K vs i7-14700KF and 9800X vs 9800X3D produce distinct canonical keys."""
    t1 = "Intel Core i7-14700 Desktop Processor"
    t2 = "Intel Core i7-14700K Desktop Processor"
    t3 = "Intel Core i7-14700KF Desktop Processor"

    k1 = make_canonical_key_string("CPU", build_canonical_key(t1, "CPU"))
    k2 = make_canonical_key_string("CPU", build_canonical_key(t2, "CPU"))
    k3 = make_canonical_key_string("CPU", build_canonical_key(t3, "CPU"))

    assert k1 == "cpu:intel:core_i7-14700"
    assert k2 == "cpu:intel:core_i7-14700k"
    assert k3 == "cpu:intel:core_i7-14700kf"
    assert len({k1, k2, k3}) == 3

    # AMD Ryzen X vs X3D suffix preservation
    amd1 = "AMD Ryzen 7 9800X Processor"
    amd2 = "AMD Ryzen 7 9800X3D Processor"

    ak1 = make_canonical_key_string("CPU", build_canonical_key(amd1, "CPU"))
    ak2 = make_canonical_key_string("CPU", build_canonical_key(amd2, "CPU"))

    assert ak1 == "cpu:amd:ryzen_7_9800x"
    assert ak2 == "cpu:amd:ryzen_7_9800x3d"
    assert ak1 != ak2


class TestThermalMaterialNotACooler:
    """Thermal paste ships under the cooler category at several stores, but it can't
    fill a build's cooler slot."""

    def test_thermal_paste_is_accessory(self):
        from matching.category_classifier import CategoryClassifier as C
        assert C.get_p_category("CPU Cooler", "Noctua NT-H2 3.5g AM5 Edition Thermal Paste") == "Accessories"
        assert C.get_p_category("CPU Cooler", "Arctic MX-6 Thermal Compound 4g") == "Accessories"
        assert C.get_p_category("CPU Cooler", "Thermalright Thermal Pad 12.8 W/mK") == "Accessories"

    def test_real_coolers_unaffected(self):
        from matching.category_classifier import CategoryClassifier as C
        assert C.get_p_category("CPU Cooler", "Deepcool AK620 Dual Tower CPU Air Cooler") == "CPU Cooler"
        assert C.get_p_category("CPU Cooler", "ZEBRONICS AIO240TW 240mm AIO Liquid Cooler") == "CPU Cooler"


class TestAudioNotAPowerSupply:
    """Audio gear filed under Power Supply reached the PSU spec pipeline and had an
    efficiency rating scraped onto it from a cross-sell block."""

    def test_audio_is_accessory(self):
        from matching.category_classifier import CategoryClassifier as C
        assert C.get_p_category("Power Supply", "Sennheiser AMBEO Soundbar Plus") == "Accessories"
        assert C.get_p_category("Power Supply", "Marshall Emberton II Wireless Bluetooth Portable Speaker") == "Accessories"

    def test_real_psus_unaffected(self):
        from matching.category_classifier import CategoryClassifier as C
        assert C.get_p_category("Power Supply", "Corsair RM850x 850W 80+ Gold Fully Modular") == "Power Supply"
        assert C.get_p_category("Power Supply", "ANT ESPORTS VS550L 550 Watt SMPS") == "Power Supply"


class TestPSUEfficiencyTrimInKey:
    """
    One PSU model name ships at several efficiency grades - ASUS "TUF Gaming 750W" in
    Bronze and Gold, Antec's HCG750 likewise. Before the trim entered the canonical key
    those variants collapsed into one model and inherited whichever rating was written
    last, so both efficiency importers had to be gap-fill-only to avoid clobbering.
    """

    def test_same_model_different_trim_separates(self):
        from matching.canonical_key_builder import build_psu_key_dict, make_canonical_key_string
        bronze = build_psu_key_dict("ASUS", "TUF Gaming", 750, "80+ Bronze")
        gold = build_psu_key_dict("ASUS", "TUF Gaming", 750, "80 PLUS Gold")
        assert make_canonical_key_string("psu", bronze) != make_canonical_key_string("psu", gold)
        # make_canonical_key_string sorts by field name, so the trim sits between brand
        # and model_number. Position is irrelevant - determinism and uniqueness are not.
        assert make_canonical_key_string("psu", gold) == "psu:asus:gold:tuf_gaming:750w"

    def test_trim_spelling_variants_collapse(self):
        """"80+ Gold", "80 PLUS GOLD" and "Gold" are one trim and must key identically."""
        from matching.canonical_key_builder import build_psu_key_dict, make_canonical_key_string
        keys = {
            make_canonical_key_string("psu", build_psu_key_dict("Corsair", "RM850x", 850, spelling))
            for spelling in ("80+ Gold", "80 PLUS GOLD", "Gold", "80plus gold", "  gOlD ")
        }
        assert len(keys) == 1

    def test_untiered_listing_groups_apart(self):
        """
        A title stating no tier is not evidence of any particular grade, so it must not
        merge into a tiered group - that would re-create the bug this fixes.
        """
        from matching.canonical_key_builder import build_psu_key_dict, make_canonical_key_string
        unknown = build_psu_key_dict("Antec", "HCG750", 750, None)
        gold = build_psu_key_dict("Antec", "HCG750", 750, "Gold")
        assert make_canonical_key_string("psu", unknown) == "psu:antec:hcg750:750w"
        assert make_canonical_key_string("psu", unknown) != make_canonical_key_string("psu", gold)

    def test_unrecognised_rating_text_is_not_guessed(self):
        """Free text naming no known tier contributes nothing rather than a guess."""
        from matching.canonical_key_builder import normalize_efficiency_trim
        assert normalize_efficiency_trim("80 PLUS") == ""
        assert normalize_efficiency_trim("high efficiency") == ""
        assert normalize_efficiency_trim("") == ""
        assert normalize_efficiency_trim(None) == ""

    def test_all_six_tiers_recognised(self):
        from matching.canonical_key_builder import normalize_efficiency_trim
        for tier in ("Titanium", "Platinum", "Gold", "Silver", "Bronze", "Standard"):
            assert normalize_efficiency_trim(f"80 PLUS {tier}") == tier.lower()

    def test_wattage_still_separates(self):
        """The trim is additional evidence, not a replacement for wattage."""
        from matching.canonical_key_builder import build_psu_key_dict, make_canonical_key_string
        w650 = build_psu_key_dict("MSI", "MAG A650BN", 650, "Bronze")
        w750 = build_psu_key_dict("MSI", "MAG A650BN", 750, "Bronze")
        assert make_canonical_key_string("psu", w650) != make_canonical_key_string("psu", w750)


class TestBrandRegistry:
    """
    Stage 1 names Corsair and ASUS reliably but is inconsistent on India-market makes,
    and a brand it cannot name becomes "Unknown" - which the brand-led canonical key
    then collapses into one coarse group. Hints turn that from recall into recognition.
    """

    def test_hint_block_names_seeded_brands(self):
        from matching.brand_registry import brand_hint_block
        block = brand_hint_block("psu")
        assert "Ant Esports" in block and "Zebronics" in block

    def test_hint_block_forbids_guessing(self):
        """
        The wording is load-bearing. Handing a model a brand list invites it to attach
        one to every title, turning a visible "Unknown" into an invisible wrong answer.
        """
        from matching.brand_registry import brand_hint_block
        block = brand_hint_block("psu").lower()
        assert "only to recognise" in block
        assert "never" in block
        assert "unknown" in block

    def test_empty_category_appends_nothing(self):
        """A category with no hints must leave its prompt byte-identical."""
        from matching.brand_registry import brand_hint_block
        assert brand_hint_block("psu", registry={}) == ""
        assert brand_hint_block("nonexistent-category", registry={"psu": ["Corsair"]}) == ""

    @staticmethod
    def _listed_names(block: str) -> list[str]:
        """
        The brand names only, not the surrounding instruction.

        Asserting against the whole block is a trap: the instruction deliberately
        contains the word "Unknown" (it tells the model to return exactly that), so a
        naive substring check for a filtered placeholder matches the instruction text
        and passes whatever the brand list holds.
        """
        lines = block.splitlines()
        i = next(i for i, ln in enumerate(lines) if ln.startswith("Brands known to appear"))
        return [n.strip() for n in lines[i + 1].split(",") if n.strip()]

    def test_placeholder_brands_never_become_hints(self):
        """"Unknown" is the failure marker - teaching it back as a brand would be circular."""
        from matching.brand_registry import brand_hint_block
        block = brand_hint_block("psu", registry={"psu": ["Unknown", "", "N/A", "Generic", "Corsair"]})
        assert self._listed_names(block) == ["Corsair"]

    def test_duplicate_spellings_collapse(self):
        from matching.brand_registry import brand_hint_block
        block = brand_hint_block("psu", registry={"psu": ["Corsair", "CORSAIR", "corsair", "Antec"]})
        assert self._listed_names(block) == ["Corsair", "Antec"]

    def test_hints_are_capped(self):
        """A prompt carrying hundreds of names costs tokens on every batch."""
        from matching.brand_registry import brand_hint_block, MAX_HINTS_PER_CATEGORY
        many = [f"Brand{i}" for i in range(MAX_HINTS_PER_CATEGORY * 3)]
        block = brand_hint_block("psu", registry={"psu": many})
        assert len(self._listed_names(block)) <= MAX_HINTS_PER_CATEGORY

    def test_missing_registry_falls_back_to_seed(self):
        """A missing or corrupt file must degrade to today's behaviour, not raise."""
        from pathlib import Path
        from matching.brand_registry import load_registry, SEED_BRANDS
        loaded = load_registry(Path("does-not-exist-anywhere.json"))
        assert loaded["psu"] == SEED_BRANDS["psu"]

    def test_cabinet_and_case_are_one_category(self):
        """
        canonical_parts stores cabinets as "case"; the extractor asks for "cabinet".
        Keying the registry on the raw string produced two entries - a seed-only one
        nothing read, and a derived one nothing seeded - so cabinet prompts silently
        carried 9 hints instead of 34.
        """
        from matching.brand_registry import brand_hint_block
        reg = {"case": ["Ant Esports", "Lian Li"]}
        assert self._listed_names(brand_hint_block("cabinet", reg)) == ["Ant Esports", "Lian Li"]
        assert brand_hint_block("cabinet", reg) == brand_hint_block("case", reg)

    def test_registry_keys_are_normalised_on_load(self):
        from matching.brand_registry import load_registry
        assert "cabinet" not in load_registry()
        assert "case" in load_registry()

    def test_identity_prompt_appends_rather_than_rewrites(self):
        """
        Hints are an optimisation appended to the end. The base prompt must survive
        intact - a category's rules are what actually drive extraction.
        """
        import services.groq_extraction_service as svc
        assert svc.identity_prompt("psu").startswith(svc.PSU_IDENTITY_BATCH_PROMPT)
        assert svc.identity_prompt("cpu").startswith(svc.CPU_IDENTITY_BATCH_PROMPT)

    def test_empty_registry_leaves_prompt_untouched(self):
        """
        The no-hints path must be byte-identical to pre-registry behaviour, so a missing
        or empty registry can never be what changes extraction.
        """
        from matching.brand_registry import brand_hint_block
        import services.groq_extraction_service as svc
        assert brand_hint_block("cpu", registry={}) == ""
        assert svc.CPU_IDENTITY_BATCH_PROMPT + brand_hint_block("cpu", registry={}) \
            == svc.CPU_IDENTITY_BATCH_PROMPT

    def test_unregistered_category_is_rejected_not_guessed(self):
        """A typo'd category must fail loudly rather than silently extract with no rules."""
        import pytest
        import services.groq_extraction_service as svc
        with pytest.raises(svc.GroqExtractionError):
            svc.identity_prompt("powersupply")


class TestPSUTrimReconciliation:
    """
    Putting the trim in the key fixes the over-merge but creates the opposite fault on
    its own: retailers print the rating inconsistently, so one real unit whose listings
    are split between "Ant Esports FG650 V2 650W 80+ Gold" and "Ant Esports FG650 V2
    650W" keys as two products. Against real data this was 47 spurious splits out of 47.
    """

    class _Row:
        """Minimal stand-in for PSUTitleExtraction - these are pure grouping rules."""
        def __init__(self, brand, model, wattage, rating, status="ok"):
            self.brand, self.model_number = brand, model
            self.wattage, self.efficiency_rating, self.status = wattage, rating, status

    def test_single_trim_resolves_for_group(self):
        from matching.psu_identity import resolve_group_trim
        rows = [
            self._Row("Ant Esports", "FG650 V2", 650, "80+ Gold"),
            self._Row("Ant Esports", "FG650 V2", 650, None),
            self._Row("Ant Esports", "FG650 V2", 650, "Gold"),
        ]
        assert resolve_group_trim(rows) == "gold"

    def test_conflicting_trims_resolve_to_nothing(self):
        """ASUS TUF Gaming 750W genuinely ships Bronze and Gold - never pick one."""
        from matching.psu_identity import resolve_group_trim
        rows = [
            self._Row("ASUS", "TUF Gaming", 750, "80+ Bronze"),
            self._Row("ASUS", "TUF Gaming", 750, "80+ Gold"),
        ]
        assert resolve_group_trim(rows) is None

    def test_no_stated_trim_resolves_to_nothing(self):
        from matching.psu_identity import resolve_group_trim
        rows = [self._Row("Circle", "Raw Power", 650, None),
                self._Row("Circle", "Raw Power", 650, "")]
        assert resolve_group_trim(rows) is None

    def test_stated_trim_is_never_overwritten(self):
        """
        A title naming a tier is evidence. A genuine Bronze listing must not be rewritten
        to Gold just because more of its siblings say Gold.
        """
        from matching.psu_identity import resolve_group_trim
        rows = [
            self._Row("MSI", "MAG A750GL", 750, "Gold"),
            self._Row("MSI", "MAG A750GL", 750, "Gold"),
            self._Row("MSI", "MAG A750GL", 750, "Bronze"),
        ]
        assert resolve_group_trim(rows) is None

    def test_reconciled_group_keys_as_one_product(self):
        """End state: the silent listing must land on the same canonical id as its siblings."""
        from matching.canonical_key_builder import build_psu_key_dict, make_canonical_key_string
        from matching.psu_identity import resolve_group_trim
        rows = [
            self._Row("Ant Esports", "FG650 V2", 650, "80+ Gold"),
            self._Row("Ant Esports", "FG650 V2", 650, None),
        ]
        trim = resolve_group_trim(rows)
        keys = {
            make_canonical_key_string(
                "psu",
                build_psu_key_dict(r.brand, r.model_number, r.wattage,
                                   r.efficiency_rating or trim),
            )
            for r in rows
        }
        assert keys == {"psu:ant_esports:gold:fg650_v2:650w"}


class TestQualifierFieldsDoNotIdentify:
    """
    disambiguate_failed_key salts a key with the product id when extraction produced
    nothing identifying, so unresolved listings never collide into one fake group.
    Adding the PSU efficiency trim to the key broke that test: a listing with no brand,
    no model and no wattage but a readable "80+ Bronze" looked like it had real content
    and keyed as psu:unknown:bronze - merging every unresolved Bronze listing into one.
    """

    def test_trim_alone_does_not_count_as_identity(self):
        from matching.canonical_key_builder import (
            build_psu_key_dict, disambiguate_failed_key, make_canonical_key_string,
        )
        a = disambiguate_failed_key(build_psu_key_dict(None, None, None, "80+ Bronze"), 101)
        b = disambiguate_failed_key(build_psu_key_dict(None, None, None, "80+ Bronze"), 202)
        assert make_canonical_key_string("psu", a) != make_canonical_key_string("psu", b)

    def test_real_identity_is_not_salted(self):
        """A key naming an actual product must stay stable across listings."""
        from matching.canonical_key_builder import (
            build_psu_key_dict, disambiguate_failed_key, make_canonical_key_string,
        )
        a = disambiguate_failed_key(build_psu_key_dict("Corsair", "RM850x", 850, "Gold"), 101)
        b = disambiguate_failed_key(build_psu_key_dict("Corsair", "RM850x", 850, "Gold"), 202)
        assert make_canonical_key_string("psu", a) == make_canonical_key_string("psu", b)
        assert "_unresolved_id" not in a

    def test_wattage_alone_still_identifies(self):
        """Only the trim was reclassified - other fields keep their existing behaviour."""
        from matching.canonical_key_builder import build_psu_key_dict, disambiguate_failed_key
        assert "_unresolved_id" not in disambiguate_failed_key(
            build_psu_key_dict(None, None, 850, None), 101
        )

    def test_other_categories_unaffected(self):
        from matching.canonical_key_builder import disambiguate_failed_key
        assert "_unresolved_id" in disambiguate_failed_key(
            {"category": "gpu", "aib_brand": "Unknown", "chipset": "", "variant_model": ""}, 7
        )


class TestProviderChain:
    """
    One provider is a single point of failure, and it fails quietly: an exhausted quota
    429s through every retry, each model is written status "failed", and Stage 2 then
    treats those rows as done. Fifteen PSU models were stuck that way.
    """

    def test_chain_is_ordered_by_measured_accuracy(self):
        """Accuracy ties at 8/8, so throughput decides: ministral-14b ~210/min, gemini ~108/min, groq rejects 5 of 6 calls."""
        from services.groq_extraction_service import provider_chain
        names = [c[0] for c in provider_chain()]
        assert names[0] == "mistral"
        assert names.index("google") < names.index("groq")

    def test_chain_skips_providers_without_keys(self):
        from services.groq_extraction_service import provider_chain
        assert all(c[3] for c in provider_chain())

    def test_default_service_uses_chain_head(self):
        """
        Scripts must not name a provider. Fifteen of them hardcoding Mistral is how the
        pipeline stayed pinned to one exhausted quota.
        """
        from services.groq_extraction_service import default_service, provider_chain
        head = provider_chain()[0]
        with default_service() as svc:
            assert (svc.api_url, svc.model) == (head[1], head[2])

    def test_service_carries_the_rest_as_fallbacks(self):
        from services.groq_extraction_service import default_service, provider_chain
        with default_service() as svc:
            assert len(svc._fallbacks) == len(provider_chain()) - 1
            assert all(f[1] != svc.api_url for f in svc._fallbacks)

    def test_provider_exhausted_is_distinct_from_extraction_failure(self):
        """
        The distinction is what stops a provider outage being recorded as a fact about
        the data - callers roll to the next provider instead of writing status "failed".
        """
        from services.groq_extraction_service import GroqExtractionError, ProviderExhausted
        assert issubclass(ProviderExhausted, GroqExtractionError)


class TestPSUPromptsRejectCybenetics:
    """
    PSU titles routinely carry two certification schemes at once - "LEADEX III GOLD UP
    ... Cybenetics Platinum Certified Gold" is 80 PLUS Gold but Cybenetics Platinum.
    Without the distinction every model read Platinum off that title. Naming the scheme
    took a fixed 8-case benchmark from mixed to 8/8 on three separate models, and cut
    real trim conflicts from 18 to 2 - the prompt mattered more than the model did.
    """

    def test_both_psu_prompts_name_the_scheme(self):
        import services.groq_extraction_service as svc
        for prompt in (svc.PSU_IDENTITY_BATCH_PROMPT, svc.PSU_SPEC_BATCH_PROMPT):
            assert "CYBENETICS" in prompt
            assert "80 PLUS" in prompt

    def test_model_name_markers_are_documented(self):
        """A tier word in the model name is the manufacturer's own marker, not noise."""
        import services.groq_extraction_service as svc
        for prompt in (svc.PSU_IDENTITY_BATCH_PROMPT, svc.PSU_SPEC_BATCH_PROMPT):
            assert '"GL"' in prompt and "Leadex III Gold" in prompt

    def test_conflict_audit_ignores_retired_groups(self):
        """
        A re-key retires a group by leaving it unreferenced, not by deleting it, and its
        stale spec row stays behind. An unfiltered audit reports those corpses as live
        conflicts - 4 of 6 reported conflicts had zero listings, including an MSI pair a
        re-key had already dissolved. find_trim_conflicts must join through products.
        """
        import inspect
        from matching import psu_identity
        src = inspect.getsource(psu_identity.find_trim_conflicts)
        assert "Product.canonical_id" in src, "audit must restrict to groups with listings"
