"""
Order-independent PC hardware compatibility engine.

Rules (compatibility_rules.py) are pairwise/aggregate relationships between spec
fields, not a pick sequence - the same rules validate a build and filter candidate
pools regardless of what order the user selects components in.

Each component slot resolves its spec fields from TWO possible sources, merged with
the *_title_extractions table taking precedence when both have a value:
  1. The category's *_title_extractions table (LLM-extracted identity + whichever
     compatibility fields were actually stated in scraped titles - e.g. RAM
     capacity/modules, PSU wattage, Cabinet form_factor, Motherboard socket/
     memory_type). Verified end-to-end against real mismatch data (see
     PROGRESS.md, 2026-08-16) and preferred as the more reliable source.
  2. The category's *_specs table - originally meant to hold curated physical
     specs from an external dataset, but currently populated with leftover
     output from the old regex-based normalizer (superseded, not otherwise
     used) for every category except CPU/Monitor, which are still genuinely
     empty. Used as a fallback for fields the LLM extraction doesn't cover
     (e.g. motherboard memory_slots, cabinet max_gpu_length_mm) and will
     become the primary source again once real curated data replaces it.
This means checks like RAM-vs-motherboard capacity/slot-count, PSU wattage sizing,
and cabinet form-factor fit can run today even though full physical specs haven't
landed yet.
"""
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.product import Product
from db.models.category_specs import (
    CabinetSpecs, CoolerSpecs, CPUSpecs, GPUSpecs, MotherboardSpecs, PSUSpecs, RAMSpecs, SSDSpecs,
)
from db.models.ram_title_extraction import RAMTitleExtraction
from db.models.gpu_title_extraction import GPUTitleExtraction
from db.models.motherboard_title_extraction import MotherboardTitleExtraction
from db.models.psu_title_extraction import PSUTitleExtraction
from db.models.cabinet_title_extraction import CabinetTitleExtraction
from db.models.cooler_title_extraction import CoolerTitleExtraction
from db.models.storage_title_extraction import StorageTitleExtraction
from domain.builder import CompatibilityWarning
from services.compatibility_rules import (
    RULES, form_factor_index, WATTAGE_HEADROOM, DEFAULT_CPU_TDP, DEFAULT_GPU_TDP,
)


def _merge(specs_obj, extraction_obj, fields: dict[str, str]):
    """Build a merged view: prefer a non-None value from extraction_obj (LLM-verified),
    else fall back to specs_obj's value. `fields` maps the unified attribute name ->
    the extraction table's (possibly differently-named) attribute name; specs_obj is
    always read via the unified name, since *_specs columns match it directly.

    extraction_obj wins when both have a value because *_specs currently holds
    uncontrolled regex-derived leftovers rather than curated data (see module
    docstring) - confirmed disagreeing with the LLM extraction on ~19% of
    motherboards' socket field. Flip this priority back once *_specs is populated
    from a real external spec source."""
    ns = SimpleNamespace()
    for unified_name, ext_name in fields.items():
        val = getattr(extraction_obj, ext_name, None) if extraction_obj else None
        if val is None and specs_obj is not None:
            val = getattr(specs_obj, unified_name, None)
        setattr(ns, unified_name, val)
    return ns


class CompatibilityEngine:
    def __init__(self, session: Session):
        self.session = session

    def _resolve_slot(self, category: str, products: list[Product]) -> list:
        """Returns merged spec views for every selected product in this slot."""
        if not products:
            return []
        ids = [p.id for p in products]
        canonical_ids = [p.canonical_id for p in products if p.canonical_id]

        if category == "cpu":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(CPUSpecs).where(CPUSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            return [
                _merge(specs.get(p.canonical_id), None, {
                    "socket": "socket", "tdp": "tdp", "cores": "cores", "threads": "threads",
                })
                for p in products
            ]

        if category == "motherboard":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(MotherboardSpecs).where(MotherboardSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            ext = {e.product_id: e for e in self.session.scalars(select(MotherboardTitleExtraction).where(MotherboardTitleExtraction.product_id.in_(ids)))}
            return [
                _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "socket": "socket", "chipset": "chipset", "form_factor": "form_factor",
                    "memory_type": "memory_type", "memory_slots": "memory_slots", "max_memory_gb": "max_memory_gb",
                })
                for p in products
            ]

        if category == "ram":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(RAMSpecs).where(RAMSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            ext = {e.product_id: e for e in self.session.scalars(select(RAMTitleExtraction).where(RAMTitleExtraction.product_id.in_(ids)))}
            return [
                _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "memory_type": "memory_type", "capacity_gb": "capacity_gb", "modules": "modules",
                    "speed_mhz": "speed_mhz",
                })
                for p in products
            ]

        if category == "gpu":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(GPUSpecs).where(GPUSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            ext = {e.product_id: e for e in self.session.scalars(select(GPUTitleExtraction).where(GPUTitleExtraction.product_id.in_(ids)))}
            return [
                _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "length_mm": "length_mm", "tdp": "tdp", "recommended_psu": "recommended_psu",
                    "chipset": "chipset",
                })
                for p in products
            ]

        if category == "psu":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(PSUSpecs).where(PSUSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            ext = {e.product_id: e for e in self.session.scalars(select(PSUTitleExtraction).where(PSUTitleExtraction.product_id.in_(ids)))}
            return [
                _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "wattage": "wattage", "form_factor": "form_factor",
                })
                for p in products
            ]

        if category == "case":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(CabinetSpecs).where(CabinetSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            ext = {e.product_id: e for e in self.session.scalars(select(CabinetTitleExtraction).where(CabinetTitleExtraction.product_id.in_(ids)))}
            return [
                _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "form_factor": "form_factor", "max_gpu_length_mm": "max_gpu_length_mm",
                    "max_cooler_height_mm": "max_cooler_height_mm", "max_psu_length_mm": "max_psu_length_mm",
                })
                for p in products
            ]

        if category == "cooler":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(CoolerSpecs).where(CoolerSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            ext = {e.product_id: e for e in self.session.scalars(select(CoolerTitleExtraction).where(CoolerTitleExtraction.product_id.in_(ids)))}
            return [
                _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "radiator_size_mm": "size_mm", "supported_sockets": "supported_sockets", "tdp_rating": "tdp_rating",
                })
                for p in products
            ]

        if category == "storage":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(SSDSpecs).where(SSDSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            ext = {e.product_id: e for e in self.session.scalars(select(StorageTitleExtraction).where(StorageTitleExtraction.product_id.in_(ids)))}
            return [
                _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "capacity_gb": "capacity_gb", "interface": "interface",
                })
                for p in products
            ]

        return []

    def _group_selections(self, product_ids: list[int]) -> dict[str, list]:
        """Group selected products by builder slot key and resolve each to its merged spec view."""
        products = list(self.session.scalars(select(Product).where(Product.id.in_(product_ids))))
        by_category: dict[str, list[Product]] = {}
        for p in products:
            key = self._slot_key(p.p_category)
            if key:
                by_category.setdefault(key, []).append(p)

        return {cat: self._resolve_slot(cat, prods) for cat, prods in by_category.items()}

    @staticmethod
    def _slot_key(p_category: str | None) -> str | None:
        return {
            "CPU": "cpu", "Motherboard": "motherboard", "RAM": "ram", "GPU": "gpu",
            "Power Supply": "psu", "Cabinet": "case", "CPU Cooler": "cooler", "Storage": "storage",
        }.get(p_category)

    @staticmethod
    def _get(value, field: str):
        return getattr(value, field, None)

    def _eval_rule(self, rule, val_a, val_b) -> CompatibilityWarning | None:
        if val_a is None or val_b is None:
            return None  # not enough data to check yet - not an error, just unknown

        fails = False
        if rule.op == "eq":
            fails = str(val_a).strip().upper() != str(val_b).strip().upper()
        elif rule.op == "le":
            fails = float(val_a) > float(val_b)
        elif rule.op == "contains_in":
            fails = str(val_a).strip().upper() not in str(val_b).strip().upper()
        elif rule.op == "form_factor_fits":
            ia, ib = form_factor_index(val_a), form_factor_index(val_b)
            fails = ia is not None and ib is not None and ia > ib

        if fails:
            return CompatibilityWarning(level=rule.level, message=rule.message(val_a, val_b))
        return None

    def validate_build(self, product_ids: list[int]) -> tuple[bool, list[CompatibilityWarning], int]:
        """Order-independent: checks whatever subset of slots is currently filled."""
        if not product_ids:
            return True, [], 0

        selections = self._group_selections(product_ids)
        warnings: list[CompatibilityWarning] = []
        compatible = True

        for rule in RULES:
            group_a = selections.get(rule.slot_a, [])
            group_b = selections.get(rule.slot_b, [])
            if not group_a or not group_b:
                continue  # rule not yet checkable - one or both slots still empty
            for item_a in group_a:
                for item_b in group_b:
                    warning = self._eval_rule(rule, self._get(item_a, rule.field_a), self._get(item_b, rule.field_b))
                    if warning:
                        warnings.append(warning)
                        if warning.level == "error":
                            compatible = False

        # Aggregate wattage check (sum, not pairwise - handled separately from RULES).
        cpu_watt = sum((self._get(c, "tdp") or DEFAULT_CPU_TDP) for c in selections.get("cpu", []))
        gpu_watt = sum((self._get(g, "tdp") or DEFAULT_GPU_TDP) for g in selections.get("gpu", []))
        estimated_wattage = cpu_watt + gpu_watt + 50  # base system draw (board/RAM/storage/fans)

        gpu_recs = [self._get(g, "recommended_psu") for g in selections.get("gpu", []) if self._get(g, "recommended_psu")]
        psu_watts = [self._get(p, "wattage") for p in selections.get("psu", []) if self._get(p, "wattage")]
        if gpu_recs and psu_watts:
            required = max(gpu_recs)
            provided = max(psu_watts)
            if provided < required:
                warnings.append(CompatibilityWarning(
                    level="warning",
                    message=f"PSU Capacity Warning: GPU recommends at least {required}W, but selected PSU is {provided}W.",
                ))
        elif psu_watts and estimated_wattage:
            provided = max(psu_watts)
            if provided < estimated_wattage + WATTAGE_HEADROOM:
                warnings.append(CompatibilityWarning(
                    level="warning",
                    message=f"Power Supply Capacity Warning: {provided}W PSU is close to or below recommended headroom for an estimated {estimated_wattage}W build draw.",
                ))

        return compatible, warnings, estimated_wattage

    def filter_candidates(self, target_slot: str, current_product_ids: list[int], candidates: list[Product]) -> list[Product]:
        """Given whatever's already selected (any slots, any order), narrow a
        candidate pool for target_slot to only those compatible with the current
        selection. Same RULES table as validate_build - just applied in filter mode."""
        selections = self._group_selections(current_product_ids)
        if not any(selections.values()):
            return candidates  # nothing selected yet, nothing to filter against

        resolved_candidates = self._resolve_slot(target_slot, candidates)
        keep: list[Product] = []

        for product, resolved in zip(candidates, resolved_candidates):
            ok = True
            for rule in RULES:
                other_slot = None
                this_field = other_field = None
                if rule.slot_a == target_slot:
                    other_slot, this_field, other_field = rule.slot_b, rule.field_a, rule.field_b
                elif rule.slot_b == target_slot:
                    other_slot, this_field, other_field = rule.slot_a, rule.field_b, rule.field_a
                else:
                    continue

                other_group = selections.get(other_slot, [])
                if not other_group or rule.level != "error":
                    continue  # only hard-filter on error-level rules; warnings stay informational

                this_val = self._get(resolved, this_field)
                for other_item in other_group:
                    other_val = self._get(other_item, other_field)
                    warning = self._eval_rule(rule, this_val if rule.slot_a == target_slot else other_val,
                                               other_val if rule.slot_a == target_slot else this_val)
                    if warning and warning.level == "error":
                        ok = False
                        break
                if not ok:
                    break

            if ok:
                keep.append(product)

        return keep
