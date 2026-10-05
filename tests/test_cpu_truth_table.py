"""CPU matching against the owner's human review (tests/fixtures/cpu_truth_table.json).

Reviewed in the CPU Truth Table on 2026-10-02/03: every listing marked correct for its
model, and listings marked as the same product grouped together (four CPUs split
across models, and MDComputers listing eleven CPUs twice). The CPU key must put every
human-confirmed product under exactly one key, and no two products under one key.
Extend the fixture as more of the catalogue is reviewed.
"""
import json
from collections import defaultdict
from pathlib import Path

from matching.cpu_identity import cpu_key

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cpu_truth_table.json"


def _products():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))["listings"]
    keys = defaultdict(set)
    for r in rows:
        if r["verdict"] != "ok":
            continue
        e = r["extracted"]
        keys[r["product"]].add(cpu_key(e["brand"], e["series"], e["model_number"], r["title"]))
    return keys


def test_each_reviewed_cpu_has_exactly_one_key():
    split = {p: k for p, k in _products().items() if len(k) > 1}
    assert not split, f"human says one CPU, matching gives several keys: {split}"


def test_no_two_reviewed_cpus_share_a_key():
    owners = defaultdict(set)
    for product, keys in _products().items():
        for k in keys:
            owners[k].add(product)
    merged = {k: p for k, p in owners.items() if len(p) > 1}
    assert not merged, f"matching merges CPUs the human kept apart: {merged}"


def test_fixture_covers_the_known_splits():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))["listings"]
    reviewed = {r["listing_id"] for r in rows}
    # TPS "9950X 3D", Clarion's "Ryzen 9" 9700X, MDComputers' brandless 225.
    assert {17054, 14711, 1551} <= reviewed
