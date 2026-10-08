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
from matching.cabinet_clearance import parse_radiator_sizes
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
from matching.board_memory import (
    MIN_DESKTOP_DIMM_SLOTS, base_chipset, board_slots, platform_max_memory_gb,
)
from matching.cooler_sockets import CURRENT_SOCKETS, normalize_sockets, socket_supported
from matching.cpu_power import cpu_max_power
from matching.gpu_power import gpu_board_power
from services.compatibility_rules import (
    RULES, FIELD_LABELS, SLOT_LABELS, cooler_kind, form_factor_index, rule_applies,
    WATTAGE_HEADROOM, DEFAULT_CPU_TDP, DEFAULT_GPU_TDP,
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
            views = []
            for p in products:
                view = _merge(specs.get(p.canonical_id), None, {
                    "socket": "socket", "tdp": "tdp", "cores": "cores", "threads": "threads",
                })
                # The PSU estimate counts a CPU at its maximum draw (matching/cpu_power.py).
                view.max_power, view.max_power_source = cpu_max_power(
                    p.canonical_id, view.socket, view.tdp)
                views.append(view)
            return views

        if category == "motherboard":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(MotherboardSpecs).where(MotherboardSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            ext = {e.product_id: e for e in self.session.scalars(select(MotherboardTitleExtraction).where(MotherboardTitleExtraction.product_id.in_(ids)))}
            views = [
                _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "socket": "socket", "chipset": "chipset", "form_factor": "form_factor",
                    "memory_type": "memory_type", "memory_slots": "memory_slots", "max_memory_gb": "max_memory_gb",
                })
                for p in products
            ]
            # Few listings state slots or maximum memory (matching/board_memory.py):
            # a Mini-ITX board has 2 slots, and a missing maximum is the platform's.
            for v in views:
                v.memory_slots = board_slots(v.memory_slots, v.form_factor)
                if v.max_memory_gb:
                    v.max_memory_source = "published"
                else:
                    v.max_memory_gb = platform_max_memory_gb(v.chipset, v.memory_type, v.memory_slots)
                    v.max_memory_source = "platform_estimate" if v.max_memory_gb else None
            return views

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
            views = []
            for p in products:
                v = _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "length_mm": "length_mm", "tdp": "tdp", "recommended_psu": "recommended_psu",
                    "chipset": "chipset",
                })
                # No listed TDP: use the chip's reference board power (matching/gpu_power.py).
                if not v.tdp:
                    v.tdp = gpu_board_power(p.canonical_id)
                views.append(v)
            return views

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
            views = [
                _merge(specs.get(p.canonical_id), ext.get(p.id), {
                    "form_factor": "form_factor", "max_gpu_length_mm": "max_gpu_length_mm",
                    "max_cooler_height_mm": "max_cooler_height_mm", "max_psu_length_mm": "max_psu_length_mm",
                    "radiator_sizes": "radiator_sizes",  # specs only - titles don't carry it
                })
                for p in products
            ]
            # Largest radiator the case takes at any mount. Pages often list only some
            # sizes, so only "bigger than anything listed" is a reliable mismatch.
            for v in views:
                sizes = parse_radiator_sizes(v.radiator_sizes)
                v.max_radiator_mm = max(sizes) if sizes else None
            return views

        if category == "cooler":
            specs = {s.canonical_id: s for s in self.session.scalars(
                select(CoolerSpecs).where(CoolerSpecs.canonical_id.in_(canonical_ids))
            )} if canonical_ids else {}
            ext = {e.product_id: e for e in self.session.scalars(select(CoolerTitleExtraction).where(CoolerTitleExtraction.product_id.in_(ids)))}
            views = []
            for p in products:
                e = ext.get(p.id)
                v = _merge(specs.get(p.canonical_id), e, {
                    "radiator_size_mm": "size_mm", "supported_sockets": "supported_sockets", "tdp_rating": "tdp_rating",
                    "height_mm": "height_mm",  # specs only - titles don't carry it
                    "cooler_type": "cooler_type",
                })
                # The extractor writes the literal "Unknown" when a title doesn't say,
                # which _merge would prefer over a real cooler_specs type. Take the
                # first source that actually knows (AIO or Air), else None.
                spec = specs.get(p.canonical_id)
                v.cooler_type = next(
                    (t for t in (getattr(e, "cooler_type", None) if e else None,
                                 getattr(spec, "cooler_type", None) if spec else None)
                     if cooler_kind(t) is not None),
                    None,
                )
                # radiator_size_mm is a fan size on air coolers, so only an AIO's counts
                # as a radiator length.
                v.aio_radiator_mm = v.radiator_size_mm if cooler_kind(v.cooler_type) == "aio" else None
                views.append(v)
            return views

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

        # Slots with no spec resolver (e.g. monitor, which has no compatibility rules)
        # still owe one view per product: filter_candidates zips this against the
        # candidate list, and an empty list would silently zip to nothing and discard
        # every candidate rather than keeping them all unconstrained.
        return [SimpleNamespace() for _ in products]

    def _group_selections(self, product_ids: list[int]) -> dict[str, list]:
        """Group selected products by builder slot key and resolve each to its merged spec view."""
        products = list(self.session.scalars(select(Product).where(Product.id.in_(product_ids))))
        by_category: dict[str, list[Product]] = {}
        for p in products:
            key = self._slot_key(p.p_category)
            if key:
                by_category.setdefault(key, []).append(p)

        selections = {}
        for cat, prods in by_category.items():
            views = self._resolve_slot(cat, prods)
            # One view per product, in order - stamp the name so messages can say
            # which part is missing a spec.
            for product, view in zip(prods, views):
                view.product_name = product.name
            selections[cat] = views
        return selections

    @staticmethod
    def _slot_key(p_category: str | None) -> str | None:
        return {
            "CPU": "cpu", "Motherboard": "motherboard", "RAM": "ram", "GPU": "gpu",
            "Power Supply": "psu", "Cabinet": "case", "CPU Cooler": "cooler", "Storage": "storage",
        }.get(p_category)

    @staticmethod
    def _get(value, field: str):
        return getattr(value, field, None)

    @staticmethod
    def _unknown(rule, value) -> str | None:
        """Why a rule input can't be used: "missing" (no value), "unrecognised"
        (a form factor we can't place on the size scale), or None when usable."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return "missing"
        if rule.op == "form_factor_fits" and form_factor_index(value) is None:
            return "unrecognised"
        return None

    @staticmethod
    def _unverified(rule, item_a, item_b, unknown_a, unknown_b) -> CompatibilityWarning:
        def part(item, slot, field, why):
            name = getattr(item, "product_name", None) or f"the selected {SLOT_LABELS.get(slot, slot)}"
            label = FIELD_LABELS.get(field, field)
            if why == "unrecognised":
                return f"{name} has an unrecognised {label} ({getattr(item, field, '')})"
            return f"{name} has no published {label}"

        parts = []
        if unknown_a:
            parts.append(part(item_a, rule.slot_a, rule.field_a, unknown_a))
        if unknown_b:
            parts.append(part(item_b, rule.slot_b, rule.field_b, unknown_b))
        pair = f"{SLOT_LABELS.get(rule.slot_a, rule.slot_a)}/{SLOT_LABELS.get(rule.slot_b, rule.slot_b)}"
        return CompatibilityWarning(
            level="unverified",
            message=f"Unverified: {' and '.join(parts)}, so {pair} fit could not be checked.",
        )

    @staticmethod
    def _estimated_max_memory(rule, item_b) -> bool:
        """The board's maximum memory is a platform estimate, not its own figure."""
        return (rule.field_b == "max_memory_gb"
                and getattr(item_b, "max_memory_source", None) == "platform_estimate")

    @staticmethod
    def _max_memory_estimate_note(ram, board, over: bool) -> CompatibilityWarning:
        board_name = getattr(board, "product_name", None) or "the selected motherboard"
        limit = board.max_memory_gb
        if over:
            ram_name = getattr(ram, "product_name", None) or "the selected RAM"
            return CompatibilityWarning(
                level="unverified",
                message=f"Unverified: {ram_name} is {float(ram.capacity_gb):g}GB, more than the {limit}GB "
                        f"platform estimate for {board_name}, which has no published maximum memory, "
                        f"so RAM/motherboard capacity could not be checked.",
            )
        slots = (f"{board.memory_slots} slots" if board.memory_slots
                 else f"{MIN_DESKTOP_DIMM_SLOTS} slots (assumed - its slot count isn't listed)")
        platform = " ".join(x for x in (base_chipset(board.chipset), board.memory_type) if x)
        return CompatibilityWarning(
            level="estimate",
            message=f"Memory limit estimate: {board_name} has no published maximum memory, so "
                    f"{limit}GB was used - a platform estimate for a {platform} board with {slots}.",
        )

    def _eval_rule(self, rule, val_a, val_b) -> CompatibilityWarning | None:
        if val_a is None or val_b is None:
            return None  # not enough data to check yet - not an error, just unknown

        fails = False
        if rule.op == "eq":
            fails = str(val_a).strip().upper() != str(val_b).strip().upper()
        elif rule.op == "le":
            fails = float(val_a) > float(val_b)
        elif rule.op == "contains_in":
            # Whole sockets, with LGA115x expanded (matching/cooler_sockets.py). A cooler
            # list with nothing recognisable falls back to the plain text check.
            supported = socket_supported(str(val_a), str(val_b))
            if normalize_sockets(str(val_b)) is None:
                supported = str(val_a).strip().upper() in str(val_b).strip().upper()
            fails = not supported
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
        memory_notes: list[CompatibilityWarning] = []  # shown with the other estimates
        compatible = True

        for rule in RULES:
            group_a = selections.get(rule.slot_a, [])
            group_b = selections.get(rule.slot_b, [])
            if not group_a or not group_b:
                continue  # rule not yet checkable - one or both slots still empty
            for item_a in group_a:
                for item_b in group_b:
                    if not rule_applies(rule, item_a, item_b):
                        continue  # e.g. tower height on an AIO - not missing, just N/A
                    val_a, val_b = self._get(item_a, rule.field_a), self._get(item_b, rule.field_b)
                    unknown_a = self._unknown(rule, val_a)
                    unknown_b = self._unknown(rule, val_b)
                    if (rule.field_b == "memory_slots" and unknown_b and not unknown_a
                            and float(val_a) <= MIN_DESKTOP_DIMM_SLOTS):
                        continue  # every desktop board has at least 2 DIMM slots
                    if self._estimated_max_memory(rule, item_b) and not unknown_a:
                        # A platform estimate is a floor, not the board's own limit: RAM
                        # within it fits; RAM above it is unknown, never an error.
                        over = float(val_a) > float(val_b)
                        (warnings if over else memory_notes).append(
                            self._max_memory_estimate_note(item_a, item_b, over))
                        continue
                    if (rule.op == "contains_in" and unknown_b and not unknown_a
                            and str(val_a).strip().upper() in CURRENT_SOCKETS):
                        # Unknown cooler sockets with a current CPU socket: almost every
                        # cooler sold today fits it, so a note, not an unverified check.
                        warnings.append(CompatibilityWarning(
                            level="estimate",
                            message=f"Cooler sockets: {getattr(item_b, 'product_name', None) or 'the selected cooler'} doesn't list its supported "
                                    f"sockets. Almost every cooler sold today fits {val_a}, but "
                                    f"check the box says {val_a}."))
                        continue
                    if unknown_a or unknown_b:
                        # Never a silent pass, never a guessed value (FIT-01).
                        warnings.append(self._unverified(rule, item_a, item_b, unknown_a, unknown_b))
                        continue
                    warning = self._eval_rule(rule, val_a, val_b)
                    if warning:
                        warnings.append(warning)
                        if warning.level == "error":
                            compatible = False

        # Aggregate wattage check (sum, not pairwise - handled separately from RULES).
        # A CPU counts at its maximum power, not its TDP: an i5-14500 is 65 W TDP and
        # 154 W at full turbo (owner decision 2026-10-06; matching/cpu_power.py).
        cpu_watt = sum((self._get(c, "max_power") or self._get(c, "tdp") or DEFAULT_CPU_TDP)
                       for c in selections.get("cpu", []))
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

        # A PSU whose wattage we don't know can't be checked against anything, so
        # say so (once a CPU or GPU gives it something to power) rather than let
        # the build read "All checks passed".
        if selections.get("cpu") or selections.get("gpu"):
            for view in selections.get("psu", []):
                if not self._get(view, "wattage"):
                    name = self._get(view, "product_name") or "the selected PSU"
                    warnings.append(CompatibilityWarning(
                        level="unverified",
                        message=f"Unverified: {name} has no published wattage, so the PSU capacity could not be checked.",
                    ))

        # FIT-03: name every part whose wattage above is a typical value rather than
        # its own listed TDP. Appended last so the list order stays deterministic:
        # RULES order, then PSU capacity, then these notes.
        for slot, default in (("cpu", DEFAULT_CPU_TDP), ("gpu", DEFAULT_GPU_TDP)):
            for view in selections.get(slot, []):
                if not self._get(view, "tdp"):  # same test the sum above uses
                    name = self._get(view, "product_name") or f"the selected {SLOT_LABELS[slot]}"
                    warnings.append(CompatibilityWarning(
                        level="estimate",
                        message=f"Wattage estimate: {name} has no listed TDP, so a typical {default} W was used.",
                    ))

        for view in selections.get("cpu", []):
            if self._get(view, "max_power_source") == "estimate":
                name = self._get(view, "product_name") or "the selected CPU"
                warnings.append(CompatibilityWarning(
                    level="estimate",
                    message=f"Wattage estimate: {name} has no published maximum power, so "
                            f"{self._get(view, 'max_power')} W (twice its {self._get(view, 'tdp')} W TDP) was used.",
                ))

        warnings.extend(memory_notes)

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
                    board = resolved if rule.slot_b == target_slot else other_item
                    if self._estimated_max_memory(rule, board):
                        continue  # an estimate may understate the board - never filter on it
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
