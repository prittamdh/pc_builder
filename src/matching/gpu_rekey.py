"""Re-key GPU listings onto matching/gpu_identity.py's keys (migration a1c7e5f90b32).

A model split by memory size (8GB and 16GB) copies the old spec row to each half and
sets memory_size_gb from the key. The mechanics are shared: matching/rekey.py.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from db.models.category_specs import GPUSpecs
from db.models.gpu_title_extraction import GPUTitleExtraction
from matching.gpu_identity import gpu_key_fields
from matching.rekey import rekey


def _memory_from_key(spec, fields):
    if "memory" in fields:
        spec.memory_size_gb = int(fields["memory"][:-2])


def rekey_gpus(session: Session, dry_run: bool = True) -> dict:
    return rekey(
        session, category="gpu", extraction_model=GPUTitleExtraction, specs_model=GPUSpecs,
        fields_for=lambda e, p: gpu_key_fields(e.brand, e.chipset, e.variant, p.name),
        brand_field="aib_brand", on_spec=_memory_from_key, dry_run=dry_run,
    )
