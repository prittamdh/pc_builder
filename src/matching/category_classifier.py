"""
Category Classifier for PC Hardware.
Classifies products into canonical categories based on name, category string, and URL.
"""
import re


PRODUCTION_CATEGORIES = [
    "Processor",
    "Motherboard",
    "Graphics Card",
    "RAM",
    "Storage",
    "Cabinet",
    "Power Supply",
    "CPU Cooler",
    "Monitor",
    "Accessories",
]


class CategoryClassifier:
    @staticmethod
    def get_p_category(raw_category: str | None = None, title: str | None = None) -> str:
        cat_str = (raw_category or "").strip()
        cat_lower = cat_str.lower()
        title_lower = (title or "").lower()
        combined = f"{cat_lower} {title_lower}"

        # 1. Processors
        if any(k in combined for k in ["processor", "cpu", "ryzen", "intel core", "threadripper", "i3-", "i5-", "i7-", "i9-", "ultra 5", "ultra 7", "ultra 9"]):
            if not any(k in combined for k in ["cooler", "fan", "motherboard", "mobo", "paste"]):
                return "Processor"

        # 2. Motherboards
        if any(k in combined for k in ["motherboard", "motherboards", "mobo", "chipset", "b450", "b550", "b650", "x570", "x670", "h610", "b760", "z790", "z890", "am4", "am5", "lga"]):
            if "cabinet" not in combined and "cooler" not in combined:
                return "Motherboard"

        # 3. Graphics Cards
        if any(k in combined for k in ["graphics card", "gpu", "rtx", "gtx", "radeon", "geforce", "vga", "rx "]):
            return "Graphics Card"

        # 4. RAM
        if any(k in combined for k in ["ram", "memory", "ddr4", "ddr5", "desktop ram", "laptop ram", "so-dimm", "sodimm"]):
            if "ssd" not in combined and "hdd" not in combined:
                return "RAM"

        # 5. Storage (SSDs & HDDs)
        if any(k in combined for k in ["ssd", "nvme", "m.2", "sata", "hdd", "hard drive", "hard disk", "storage"]):
            return "Storage"

        # 6. Cabinets / Cases
        if any(k in combined for k in ["cabinet", "case", "chassis", "tower"]):
            return "Cabinet"

        # 7. Power Supply / SMPS
        if any(k in combined for k in ["power supply", "psu", "smps", "80+"]):
            return "Power Supply"

        # 8. CPU Coolers
        if any(k in combined for k in ["cooler", "cooling", "liquid cooler", "air cooler", "aio", "radiator", "fan"]):
            return "CPU Cooler"

        # 9. Monitors
        if any(k in combined for k in ["monitor", "display", "screen"]):
            return "Monitor"

        # 10. Default / Peripherals
        return "Accessories"
