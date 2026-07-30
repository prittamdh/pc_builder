"""
Category Classifier for PC Hardware.
Classifies raw store/target category strings into canonical p_category values via direct dictionary mapping.
"""

PRODUCTION_CATEGORIES = [
    "CPU",
    "Motherboard",
    "GPU",
    "RAM",
    "Storage",
    "Cabinet",
    "Power Supply",
    "CPU Cooler",
    "Monitor",
    "Accessories",
]

# Direct 1-to-1 Exact Category Mapping Dictionary (No Title Regex Normalization)
CATEGORY_MAPPING = {
    # CPUs
    "CPU": "CPU",
    "Processor": "CPU",
    "Desktop Processors": "CPU",
    "Intel Processor": "CPU",
    "AMD Processor": "CPU",
    "Threadripper Processor": "CPU",
    
    # GPUs
    "GPU": "GPU",
    "Graphics Card": "GPU",
    "Graphics Card (NVIDIA)": "GPU",
    "Graphics Card (AMD)": "GPU",
    "AMD Graphics Card": "GPU",
    "NVIDIA RTX 50 Series": "GPU",
    "NVIDIA RTX 30 Series": "GPU",
    
    # Motherboards
    "Motherboard": "Motherboard",
    "Motherboards": "Motherboard",
    "Intel Motherboard": "Motherboard",
    "AMD Motherboard": "Motherboard",
    
    # RAM
    "RAM": "RAM",
    "Desktop RAM": "RAM",
    "Laptop RAM": "RAM",
    "Desktop RAM (DDR4)": "RAM",
    "Desktop RAM (DDR5)": "RAM",
    "Laptop RAM (DDR4)": "RAM",
    "Laptop RAM (DDR5)": "RAM",
    
    # Storage
    "Storage": "Storage",
    "SSD": "Storage",
    "HDD": "Storage",
    "Internal HDD": "Storage",
    "External HDD": "Storage",
    "Internal SSD": "Storage",
    "External SSD": "Storage",
    "NVMe SSD": "Storage",
    "M.2 NVMe SSD": "Storage",
    "M.2 SSD": "Storage",
    "Gen3 NVMe SSD": "Storage",
    "Gen4 NVMe SSD": "Storage",
    "Gen5 NVMe SSD": "Storage",
    "Laptop SSD": "Storage",
    "External Portable HDD": "Storage",
    "External Portable SSD": "Storage",
    "External Hard Disk": "Storage",
    "Hard Drive": "Storage",
    "SATA SSD": "Storage",
    '2.5" SATA SSD': "Storage",
    
    # Cabinets
    "Cabinet": "Cabinet",
    "Cabinet Case": "Cabinet",
    
    # Power Supply
    "PSU": "Power Supply",
    "Power Supply": "Power Supply",
    "Power Supply / SMPS": "Power Supply",
    
    # CPU Coolers
    "CPU Cooler": "CPU Cooler",
    "CPU Air Cooler": "CPU Cooler",
    "CPU Liquid Cooler": "CPU Cooler",
    "Cooling System": "CPU Cooler",
    "Cooling Systems": "CPU Cooler",
    
    # Monitors
    "Monitor": "Monitor",
    
    # Accessories & Peripherals
    "Gaming Headset": "Accessories",
    "Wireless Router": "Accessories",
    "Accessories": "Accessories",
}


class CategoryClassifier:
    @staticmethod
    def get_p_category(raw_category: str | None = None, title: str | None = None) -> str:
        if not raw_category:
            return "Accessories"
            
        cleaned_cat = raw_category.strip()
        
        # Direct Exact Match
        if cleaned_cat in CATEGORY_MAPPING:
            return CATEGORY_MAPPING[cleaned_cat]
            
        # Case-Insensitive Lookup Fallback
        c_low = cleaned_cat.lower()
        for k, v in CATEGORY_MAPPING.items():
            if k.lower() == c_low:
                return v

        return "Accessories"

