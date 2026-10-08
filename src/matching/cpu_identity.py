"""CPU identity: which listings are the same processor.

The key was brand + series + model number, all from the LLM. A model number already
names a CPU, so the series only added ways to split one: the review of live data on
2026-10-02 found a 9700X labelled "Ryzen 9", a Core Ultra 5 225 and a 5700X whose
brand came back "Unknown", and TPS's "9950X 3D" read as a 9950X in a "Ryzen 9 3D"
series. The key is now brand + model number, with the brand checked against the
title, and PRO kept where it marks a different chip (Ryzen 7 PRO 8700G).
"""
from __future__ import annotations

import re

from matching.canonical_key_builder import make_canonical_key_string

_AMD_WORDS = re.compile(r"\b(ryzen|threadripper|athlon|epyc|amd)\b", re.I)
_INTEL_WORDS = re.compile(r"\b(intel|core|xeon|pentium|celeron)\b", re.I)


def normalize_model(model_number: str | None, title: str) -> str:
    model = re.sub(r"[\s\-_]+", "", (model_number or "").lower())
    # "i5-14400F" -> "14400f"; Core Ultra names carry no prefix worth keeping.
    model = re.sub(r"^(?:core)?(?:i[3579]|ultra[3579]?)", "", model)
    # "9950X 3D" in the title, or a model that lost its 3D to the series field.
    if model and not model.endswith("3d") and re.search(
            rf"\b{re.escape(model)}\s?3d\b", (title or "").lower()):
        model += "3d"
    return model


def infer_brand(brand: str | None, title: str) -> str:
    text = f"{title or ''}"
    if _AMD_WORDS.search(text):
        return "AMD"
    if _INTEL_WORDS.search(text):
        return "Intel"
    b = (brand or "").strip()
    return b if b and b.lower() != "unknown" else "Unknown"


def cpu_key_fields(brand: str | None, series: str | None, model_number: str | None,
                   title: str) -> dict:
    fields = {
        "category": "cpu",
        "brand": infer_brand(brand, title),
        "model_number": normalize_model(model_number, title),
    }
    is_threadripper = "threadripper" in f"{series or ''} {title or ''}".lower()
    if not is_threadripper and re.search(r"\bpro\b", f"{series or ''} {title or ''}", re.I):
        fields["pro"] = "pro"
    return fields


def cpu_key(brand, series, model_number, title) -> str:
    return make_canonical_key_string("cpu", cpu_key_fields(brand, series, model_number, title))
