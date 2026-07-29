"""
Category Classifier for PC Hardware.
Classifies products into canonical categories based on name, category string, and URL.
"""
import re


CATEGORIES = [
    "CPU",
    "GPU",
    "Motherboard",
    "RAM",
    "SSD",
    "HDD",
    "PSU",
    "Cabinet",
    "CPU Cooler",
    "Monitor",
    "Keyboard",
    "Mouse",
    "Accessories",
]


PATTERN_MAP = [
    # GPU / Graphics Cards
    (r"\b(rtx\s?\d{4}|rx\s?\d{4}|graphics\ card|vga|gpu|geforce|radeon)\b", "GPU"),
    
    # CPU / Processors
    (r"\b(ryzen\s?\d{4}|intel\ core|processor|cpu|i3-|i5-|i7-|i9-|core\ ultra)\b", "CPU"),
    
    # CPU Coolers
    (r"\b(aio|liquid\ cooler|cpu\ cooler|air\ cooler|radiator|240mm|360mm|420mm|hyper\ 212|ak620|frozen\ prism)\b", "CPU Cooler"),
    
    # Cabinets / Cases
    (r"\b(cabinet|case|chassis|mid\ tower|full\ tower|mini\ itx\ case|atx\ case|matx\ case)\b", "Cabinet"),
    
    # Monitors
    (r"\b(monitor|display|1440p|4k\ monitor|oled\ monitor|ips\ panel|curved\ monitor|\d{2}\s?inch\ monitor|\d{2}\"\ monitor|hz)\b", "Monitor"),
    
    # Keyboard & Mouse
    (r"\b(mechanical\ keyboard|keyboard|keychron)\b", "Keyboard"),
    (r"\b(mouse|wireless\ mouse|gaming\ mouse|mx\ master)\b", "Mouse"),
]


class CategoryClassifier:
    @staticmethod
    def classify(name: str, category_raw: str | None = None, url: str | None = None) -> str:
        text = f"{name} {category_raw or ''} {url or ''}".lower()

        for pattern, cat in PATTERN_MAP:
            if re.search(pattern, text, re.IGNORECASE):
                return cat

        return "Accessories"
