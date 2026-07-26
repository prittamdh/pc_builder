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
    
    # Motherboards
    (r"\b(motherboard|mainboard|b650|b850|x870|z890|z790|b760|a620|lga1700|am5|am4)\b", "Motherboard"),
    
    # RAM / Memory
    (r"\b(ddr5|ddr4|ram|memory\ kit|desktop\ memory|6000mhz|5600mhz|3200mhz|cl30|cl36)\b", "RAM"),
    
    # SSD / Storage
    (r"\b(nvme|m\.2|ssd|solid\ state\ drive|pcie\ 4\.0\ ssd|pcie\ 5\.0\ ssd|gen4\ ssd|gen5\ ssd)\b", "SSD"),
    
    # HDD
    (r"\b(hard\ drive|hdd|barracuda|ironwolf|wd\ blue|wd\ red|3\.5\ inch\ hdd)\b", "HDD"),
    
    # PSU / Power Supply
    (r"\b(psu|power\ supply|smps|80\+\ gold|80\+\ bronze|atx\ 3\.0|atx\ 3\.1|modular\ psu|\d{3,4}w\ psu|\d{3,4}w\ smps)\b", "PSU"),
    
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
