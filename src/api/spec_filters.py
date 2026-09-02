"""Spec-level filtering for the catalog.

The nine `*_specs` tables hold real, extracted hardware attributes but nothing ever
exposed them for browsing, so a shopper could search titles and nothing else. Filtering
on socket, VRAM, wattage or memory type is the core of what a parts catalog is for.

Specs are keyed by `canonical_id` (one row per model, not per listing), so filtering
joins products to the spec table for their category on that key. A product with no
canonical_id, or a model with no extracted specs, simply doesn't match a spec filter -
it is not silently treated as matching.
"""

from db.models.category_specs import (
    CabinetSpecs,
    CoolerSpecs,
    CPUSpecs,
    GPUSpecs,
    MonitorSpecs,
    MotherboardSpecs,
    PSUSpecs,
    RAMSpecs,
    SSDSpecs,
)

ENUM = "enum"
RANGE = "range"

# p_category -> (spec model, {filter name: (column name, kind)})
# Only fields a shopper would actually narrow by. Extraction bookkeeping columns
# (confidence, llm_model, raw_response, status) are deliberately not filterable.
SPEC_FILTERS: dict[str, tuple[type, dict[str, tuple[str, str]]]] = {
    # Field order IS the filter order shown to the user, and it is deliberate: each
    # category starts with the decision that constrains everything after it. Picking a
    # socket rules out most motherboards, so it comes before form factor and chipset;
    # picking a wattage rules out most PSUs, so it comes before efficiency. Brand is
    # always last - it narrows least and is the thing shoppers are most often flexible
    # about. Any filter can be skipped; the ones below it simply stay wide.
    "CPU": (CPUSpecs, {
        "socket": ("socket", ENUM),
        "cores": ("cores", RANGE),
        "tdp": ("tdp", RANGE),
        "threads": ("threads", RANGE),
        "brand": ("brand", ENUM),
    }),
    "Motherboard": (MotherboardSpecs, {
        "socket": ("socket", ENUM),
        "form_factor": ("form_factor", ENUM),
        "chipset": ("chipset", ENUM),
        "memory_type": ("memory_type", ENUM),
        "memory_slots": ("memory_slots", RANGE),
        "brand": ("brand", ENUM),
    }),
    "GPU": (GPUSpecs, {
        "chipset": ("chipset", ENUM),
        "memory_size_gb": ("memory_size_gb", RANGE),
        "memory_type": ("memory_type", ENUM),
        "tdp": ("tdp", RANGE),
        "brand": ("brand", ENUM),
    }),
    "RAM": (RAMSpecs, {
        "memory_type": ("memory_type", ENUM),
        "capacity_gb": ("capacity_gb", RANGE),
        "speed_mhz": ("speed_mhz", RANGE),
        "modules": ("modules", RANGE),
        "brand": ("brand", ENUM),
    }),
    "Storage": (SSDSpecs, {
        "interface": ("interface", ENUM),
        "capacity_gb": ("capacity_gb", RANGE),
        "form_factor": ("form_factor", ENUM),
        "brand": ("brand", ENUM),
    }),
    "Power Supply": (PSUSpecs, {
        "wattage": ("wattage", RANGE),
        "efficiency_rating": ("efficiency_rating", ENUM),
        "modularity": ("modularity", ENUM),
        "form_factor": ("form_factor", ENUM),
        "brand": ("brand", ENUM),
    }),
    "CPU Cooler": (CoolerSpecs, {
        "cooler_type": ("cooler_type", ENUM),
        "radiator_size_mm": ("radiator_size_mm", RANGE),
        "tdp_rating": ("tdp_rating", RANGE),
        "brand": ("brand", ENUM),
    }),
    "Cabinet": (CabinetSpecs, {
        "form_factor": ("form_factor", ENUM),
        "max_gpu_length_mm": ("max_gpu_length_mm", RANGE),
        "brand": ("brand", ENUM),
    }),
    "Monitor": (MonitorSpecs, {
        "screen_size_inch": ("screen_size_inch", RANGE),
        "resolution": ("resolution", ENUM),
        "refresh_rate_hz": ("refresh_rate_hz", RANGE),
        "panel_type": ("panel_type", ENUM),
        "brand": ("brand", ENUM),
    }),
}


def spec_model_for(p_category: str | None):
    """(model, fields) for a category, or (None, {}) if it has no spec table."""
    if not p_category:
        return None, {}
    for name, (model, fields) in SPEC_FILTERS.items():
        if name.lower() == p_category.lower():
            return model, fields
    return None, {}


def parse_spec_params(query_params, fields: dict[str, tuple[str, str]]) -> list[tuple]:
    """Read `spec_*` query params into (column_name, kind, op, value) tuples.

    Accepts `spec_socket=AM5` for enum fields and `spec_cores_min=8` /
    `spec_cores_max=16` for range fields. Unknown names are ignored rather than
    rejected, so a stale bookmark degrades to a broader search instead of a 422.
    """
    parsed = []
    for key, raw in query_params.multi_items():
        if not key.startswith("spec_") or raw == "":
            continue
        name = key[len("spec_"):]

        op = "eq"
        if name.endswith("_min"):
            name, op = name[:-4], "min"
        elif name.endswith("_max"):
            name, op = name[:-4], "max"

        field = fields.get(name)
        if field is None:
            continue
        column, kind = field

        if kind == RANGE:
            try:
                value = float(raw)
            except ValueError:
                continue
            # A bare value on a numeric field means "exactly this".
            parsed.append((column, kind, op, value))
        else:
            if op != "eq":
                continue
            parsed.append((column, kind, "eq", raw))
    return parsed


def apply_spec_filters(stmt, model, parsed: list[tuple]):
    """Add WHERE clauses for parsed spec filters. Caller has already joined `model`."""
    for column_name, kind, op, value in parsed:
        column = getattr(model, column_name)
        if kind == RANGE:
            if op == "min":
                stmt = stmt.where(column >= value)
            elif op == "max":
                stmt = stmt.where(column <= value)
            else:
                stmt = stmt.where(column == value)
        else:
            # Case-insensitive: extraction writes "AM5"/"am5", "ATX"/"atx" alike.
            stmt = stmt.where(column.ilike(str(value)))
    return stmt
