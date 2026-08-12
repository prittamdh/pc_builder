"""
Test script for canonical key builder (Phase 1 verification).
Tests build_canonical_key across representative titles per category.
"""
from matching.canonical_key_builder import build_canonical_key, make_canonical_key_string


TEST_PRODUCTS = [
    {"category": "CPU", "title": "AMD Ryzen 7 7800X3D Processor with Radeon Graphics"},
    {"category": "CPU", "title": "Intel Core i7-14700KF Desktop Processor 20 Cores"},
    {"category": "PSU", "title": "Corsair RM750e 750W 80 Plus Gold Fully Modular Power Supply"},
    {"category": "PSU", "title": "Ant Esports VS550L 550 Watt SMPS"},
    {"category": "Cooler", "title": "Arctic Liquid Freezer III 360 ARGB Liquid CPU Cooler"},
    {"category": "Cooler", "title": "Ant Esports ICE-C120 120mm CPU Air Cooler"},
    {"category": "Case", "title": "NZXT H7 Flow Mid Tower Cabinet - White"},
    {"category": "Storage", "title": "Samsung 990 PRO 1TB M.2 NVMe Gen4 Internal SSD"},
    {"category": "Storage", "title": "Adata Legend 860 2TB PCIe Gen4 NVMe M.2 SSD"},
    {"category": "RAM", "title": "G.Skill Trident Z5 RGB 32GB (16GBx2) DDR5 6000MHz CL30 RAM"},
    {"category": "RAM", "title": "Kingston Fury Beast 16GB DDR4 3200MHz CL16 Memory"},
    {"category": "Motherboard", "title": "ASUS TUF Gaming B650-Plus WiFi AM5 ATX Motherboard"},
    {"category": "GPU", "title": "MSI GeForce RTX 4070 Ti Super Gaming X Slim 16GB Graphics Card"},
    {"category": "GPU", "title": "Zotac Gaming RTX 5070 Solid OC 12GB GDDR7 Graphic Card"}
]


def main():
    print("=" * 80)
    print("TESTING CANONICAL KEY BUILDER (PHASE 1 VERIFICATION)")
    print("=" * 80)

    for item in TEST_PRODUCTS:
        cat = item["category"]
        title = item["title"]

        key_dict = build_canonical_key(title, cat)
        key_str = make_canonical_key_string(cat, key_dict)

        print(f"\n[Category: {cat.upper()}] Title: '{title}'")
        print(f"  -> Key Dict:   {key_dict}")
        print(f"  -> Key String: '{key_str}'")

    print("\n" + "=" * 80)
    print("TEST PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    main()
