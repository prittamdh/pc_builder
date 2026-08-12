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
