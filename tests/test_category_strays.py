"""Listings whose title plainly names another kind of product (owner review 2026-10-08).

Stores file SSDs, CCTV supplies and PSU testers under Power Supply, monitors and
coolers under Cabinet, and so on. A re-scrape sets p_category from the classifier
every time, so the classifier itself has to file them right or a hand fix is undone.
"""
import pytest

from matching.category_classifier import CategoryClassifier
from pipeline.identity_audit import category_strays


# (store category, title, where it belongs) - the listings moved by hand.
STRAYS = [
    ("Power Supply", "Western Digital WD Green 120gb M.2  SATA SSD", "Storage"),
    ("Power Supply", "Western Digital Black SN850X 2TB M.2 NVMe Gen4 SSD (with Heatsink)", "Storage"),
    ("Power Supply", 'Transcend 250GB SSD225S 2.5" Internal Sata SSD Sata III 6Gb/s', "Storage"),
    ("Power Supply", 'Transcend 512GB SSD230 SATA III 2.5" Internal SSD', "Storage"),
    ("Power Supply", "MSI Pro Z790-P WIFI DDR4 Intel Motherboard", "Motherboard"),
    ("Power Supply", "Dell WM118 Wireless Mouse (Black)", "Accessories"),
    ("Power Supply", "Thermaltake Dr. Power III PSU Tester Tool", "Accessories"),
    ("Power Supply", "Lapcare LCC‑303 4 Channel CCTV SMPS 12–14.5V Multiport Power Supply with Overload Protection", "Accessories"),
    ("Power Supply", "Lapcare 8 Channel CCTV SMPS Multiport LCC‑306 12V 3.5A High‑Efficiency Power Supply", "Accessories"),
    ("Power Supply", "CP PLUS CP-DPS-PD16-12D 16 Channel Power Supply for CCTV Cameras", "Accessories"),
    ("Power Supply", "CP PLUS CP-DPS-PD04V2-12D 4 Channel Power Supply for CCTV Systems", "Accessories"),
    ("Power Supply", "CP PLUS CP-DPS-MD200-12D 20A 240W 12V DC Metal Case Power Supply for CCTV", "Accessories"),
    ("Power Supply", "CP PLUS CP-DPS-MD200P-12D 240W 12V DC Metal Case Power Supply for CCTV Systems", "Accessories"),
    ("Cabinet", 'LG UltraGear 27GX790A-B 27" 480Hz OLED QHD 1440P Gaming Monitor', "Monitor"),
    ("Cabinet", "Deepcool AK700 Digital NYX CPU Air Cooler", "CPU Cooler"),
    ("Cabinet", "Antec Symphony 360 ARGB 360mm Liquid CPU Cooler - Black", "CPU Cooler"),
    ("Cabinet", "Lian Li O11 Vision-M 9.2 Inches LCD Screen", "Accessories"),
    ("Cabinet", "Lian Li O11 Vision-M 9.2 Inches White LCD Screen", "Accessories"),
    ("Cabinet", "Lian Li 8.8 Inch Universal LCD Screen for PC", "Accessories"),
    ("Cabinet", "Lian Li 8.8 Inch White Universal LCD Screen for PC", "Accessories"),
    ("Cabinet", "Thermaltake G6 Direct Drive Racing Wheel with Pedals Bundle", "Accessories"),
    ("CPU Cooler", "SanDisk Ultra CZ48 SDCZ48-256G-U46 256GB USB 3.0 Pen Drive (Black)", "Accessories"),
    ("CPU Cooler", "ZEBRONICS FC120A Low Profile Cooler Fan with Heat Sinks Cabinet Cooler  (Black)", "Accessories"),
    ("CPU Cooler", "HYTE Y60 Distro ARGB Distribution Plate", "Accessories"),
    ("CPU Cooler", "HYTE Push Connects Fittings Black 6 Pack", "Accessories"),
    ("Motherboard", "AMD Ryzen 7 7800X3D Gaming Processor OEM Pack No Stock cooler- FRESH UNIT", "CPU"),
    ("Storage", "Crucial Pro OC 32GB (16GBx2) DDR5 CL36 6000MHz RAM (White)", "RAM"),
    # Moved out of GPU by f1b4d6e2a830; without a rule the next scrape put it back.
    ("GPU", "AMD Radeon FirePro S400 Synchronization Module", "Accessories"),
    ("Storage", "[RePacked] ORICO Transparent -Free USB3.1 Type-C Gen2 10Gbps to m.2 SSD Enclosure for Intel 660p NVMe m-Key SSD up to 2T", "Accessories"),
]


@pytest.mark.parametrize("store_category, title, expected", STRAYS)
def test_a_title_naming_another_category_wins(store_category, title, expected):
    assert CategoryClassifier.get_p_category(store_category, title) == expected


# Real parts whose titles mention another category's words in passing. Brand names
# (Cooler Master), bundled extras, slots and connectors must not move them.
GENUINE = [
    ("Power Supply", "Cooler Master MWE Gold 850 V2 Full Modular 80 Plus Gold ATX 3.1 Power Supply"),
    ("Power Supply", "CORSAIR CX750 750W  80 Plus Bronze SMPS Power Supply with 120mm Silent Fan"),
    ("Power Supply", "Cooler Master Mwe 450 Bronze – V2 230V Psu (Mpe-4501-Acabw-Bin)"),
    ("Power Supply", "Super Flower Leadex VII XP 1000W 80+ Platinum, Full Modular, ATX 3.1, W/12V-2 * 6 Cable"),
    ("CPU", "AMD Ryzen 7 7800X3D Gaming Processor OEM Pack no stock cooler"),
    ("CPU", "Intel Core i5-8500 8400T Desktop Processor LGA1151 Socket (Thermal Paste Included) (Pulled Out)"),
    ("GPU", "Zotac GeForce RTX 5090 Arcticstorm AIO 32Gb GDDR7 Graphics Card (ZT-B50900K-30P)"),
    ("GPU", "Nextron GTX 1050Ti 4GB DDR5 Dual fan Graphics Card"),
    ("GPU", "HP NVIDIA RTX A400 4GB with Mini Bracket 4mDP Graphics (AV8J3AA)"),
    ("Cabinet", "Cooler Master CMP 520 (ATX) Mid Tower Cabinet With Tempered Glass Side Panel And ARGB Controller"),
    ("Cabinet", "Hyte Y40 TG Mid-Tower ATX Cabinet with PCIe 4.0 Riser (White)"),
    ("Cabinet", "CONSISTENT GAMING PC CASE (CIG2007) LEGENDOR White including two 12cm ARGB fans on the motherboard plate"),
    ("Cabinet", "Consistent Inferno Gaming Cabinet 2002 | Support : Micro ATX/ Mini ATX / ATX Motherboard"),
    ("Cabinet", "Lian Li O11 Dynamic Evo XL – Black"),
    ("Motherboard", "EVM EVMH310 DDR4 Motherboard With Nvme Slot"),
    ("Motherboard", "Asus ROG Crosshair X870E Edition 20 WiFi7 E-ATX Motherboard with RYUJIN 360 CPU Cooler"),
    ("Motherboard", "ASUS ROG STRIX B650-A Gaming WiFi AM5 Motherboard for AMD Ryzen 7000 Series Processors"),
    ("Monitor", "Dell UltraSharp U2725QE 27\" 2160p 4K UHD 120Hz IPS Thunderbolt Hub Monitor"),
    ("Monitor", "Cooler Master GA271 27 Inch 2K Wqhd Gaming Monitor (CMI-GA271)"),
    ("Storage", "SEAGATE One Touch HUB 4TB Type-C 5400RPM External Hard Drive ( HDD )"),
    ("CPU Cooler", "Gamdias CHIONE P2-360R AIO Liquid Cooler with Triple 120mm RGB Silent Fan and Remote Controller"),
    ("CPU Cooler", "ProLab Design PL-LGA4677-4U CPU Cooler for 4U Chassis"),
    # The store's title is wrong (a Titan 420 RX is an AIO); the owner kept it as a cooler.
    ("CPU Cooler", "CORSAIR TITAN 420 RX RGB DDR4 RAM With Heatsink"),
    ("RAM", "Corsair Vengeance RGB 32GB (2x16GB) DDR5 6000MHz Desktop RAM"),
]


@pytest.mark.parametrize("store_category, title", GENUINE)
def test_a_passing_mention_keeps_the_store_category(store_category, title):
    assert CategoryClassifier.get_p_category(store_category, title) == store_category


def test_the_audit_flags_listings_whose_title_names_another_category():
    rows = [
        (20710, "Power Supply", "Thermaltake Dr. Power III PSU Tester Tool"),
        (16760, "Power Supply", "Western Digital WD Green 120gb M.2  SATA SSD"),
        (4380, "Power Supply", "Cooler Master MWE 750 - V2 Full Modular Gold 80 Plus ATX Power Supply"),
        (16929, "Cabinet", 'LG UltraGear 27GX790A-B 27" 480Hz OLED QHD 1440P Gaming Monitor'),
        (16760, "Storage", "Western Digital WD Green 120gb M.2  SATA SSD"),
    ]
    assert category_strays(rows) == [
        (20710, "Power Supply", "Accessories"),
        (16760, "Power Supply", "Storage"),
        (16929, "Cabinet", "Monitor"),
    ]


def test_the_audit_also_catches_the_older_guards():
    # Thermal paste filed as a cooler predates this audit; it is still a stray.
    rows = [(5733, "CPU Cooler", "Noctua NT-H2 3.5g AM5 Edition Thermal Paste")]
    assert category_strays(rows) == [(5733, "CPU Cooler", "Accessories")]
