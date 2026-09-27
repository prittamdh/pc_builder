import pytest

from pipeline.identity_audit import psu_watts_from_title, size_conflicts, storage_gb_from_title


@pytest.mark.parametrize("title, gb", [
    ("Samsung 990 Pro 2TB M.2 NVMe Gen4 SSD", 2000),
    ("WD Blue SN580 500GB NVMe SSD", 500),
    ("Crucial P3 Plus 1 TB PCIe 4.0", 1000),
    ("Seagate Barracuda 1.5TB HDD", 1500),
    ("Kingston NV3 NVMe SSD", None),
])
def test_storage_capacity(title, gb):
    assert storage_gb_from_title(title) == gb


@pytest.mark.parametrize("title, w", [
    ("Corsair RM850x Gold ATX 3.1 Fully Modular SMPS 850W", 850),
    ("Ant Value ECO400 400 Watt SMPS", 400),
    ("Deepcool PN750M 750 W 80 Plus Gold", 750),
    ("Cooler Master MWE Gold V2", None),
])
def test_psu_watts(title, w):
    assert psu_watts_from_title(title) == w


def test_mixed_sizes_are_reported():
    rows = [
        ("GPU", "gpu:asus:rx_9060_xt:dual", "ASUS Dual RX 9060 XT 8GB"),
        ("GPU", "gpu:asus:rx_9060_xt:dual", "ASUS Dual RX 9060 XT 16GB"),
        ("Storage", "ssd:a", "Samsung 990 Pro 1TB"),
        ("Storage", "ssd:a", "Samsung 990 Pro 1 TB NVMe"),
        ("Power Supply", "psu:a", "RM850x 850W"),
        ("Power Supply", "psu:a", "RM750x 750W"),
    ]
    assert size_conflicts(rows) == {
        "gpu:asus:rx_9060_xt:dual": {8, 16},
        "psu:a": {750, 850},
    }


def test_titles_without_a_size_never_conflict():
    rows = [("GPU", "g", "MSI RTX 5070 Ventus"), ("GPU", "g", "MSI RTX 5070 Ventus 12GB")]
    assert size_conflicts(rows) == {}
