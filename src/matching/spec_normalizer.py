"""
Specification Normalizer for PC Hardware.
Converts raw specification key-value pairs and product titles into canonical typed spec dicts.
"""
import re


class SpecNormalizer:

    @staticmethod
    def normalize_cpu(name: str, raw_specs: dict) -> dict:
        text = f"{name} {raw_specs}".lower()
        specs = {}

        # Socket
        if "am5" in text:
            specs["socket"] = "AM5"
        elif "lga1700" in text or "lga 1700" in text or "14th gen" in text or "13th gen" in text or "12th gen" in text:
            specs["socket"] = "LGA1700"
        elif "lga1851" in text or "core ultra" in text:
            specs["socket"] = "LGA1851"
        elif "am4" in text:
            specs["socket"] = "AM4"

        # Cores & Threads
        cores_match = re.search(r"(\d+)\s?-?\s?(core|cores)", text)
        if cores_match:
            specs["cores"] = int(cores_match.group(1))

        threads_match = re.search(r"(\d+)\s?-?\s?(thread|threads)", text)
        if threads_match:
            specs["threads"] = int(threads_match.group(1))

        # Boost Clock
        clock_match = re.search(r"(\d+\.\d+)\s?ghz", text)
        if clock_match:
            specs["boost_clock"] = float(clock_match.group(1))

        # TDP
        tdp_match = re.search(r"(\d+)\s?w\b", text)
        if tdp_match:
            specs["tdp"] = int(tdp_match.group(1))

        # Integrated Graphics
        specs["integrated_graphics"] = False if "f" in name.split() or "no graphics" in text else True

        return specs

    @staticmethod
    def normalize_gpu(name: str, raw_specs: dict) -> dict:
        text = f"{name} {raw_specs}".lower()
        specs = {}

        # Chipset / Model
        if "rtx 5090" in text:
            specs["chipset"] = "RTX 5090"
            specs["memory_size_gb"] = 32
            specs["recommended_psu"] = 1000
        elif "rtx 5080" in text:
            specs["chipset"] = "RTX 5080"
            specs["memory_size_gb"] = 16
            specs["recommended_psu"] = 850
        elif "rtx 5070 ti" in text:
            specs["chipset"] = "RTX 5070 Ti"
            specs["memory_size_gb"] = 16
            specs["recommended_psu"] = 750
        elif "rtx 5070" in text:
            specs["chipset"] = "RTX 5070"
            specs["memory_size_gb"] = 12
            specs["recommended_psu"] = 650
        elif "rtx 5060 ti" in text:
            specs["chipset"] = "RTX 5060 Ti"
            specs["memory_size_gb"] = 8
            specs["recommended_psu"] = 650
        elif "rtx 5060" in text:
            specs["chipset"] = "RTX 5060"
            specs["memory_size_gb"] = 8
            specs["recommended_psu"] = 550

        # Memory Type
        specs["memory_type"] = "GDDR7" if "gddr7" in text else "GDDR6"

        return specs

    @staticmethod
    def normalize_motherboard(name: str, raw_specs: dict) -> dict:
        text = f"{name} {raw_specs}".lower()
        specs = {}

        # Socket
        if "am5" in text or "b650" in text or "x870" in text or "b850" in text or "x670" in text:
            specs["socket"] = "AM5"
            specs["memory_type"] = "DDR5"
        elif "z890" in text or "lga1851" in text:
            specs["socket"] = "LGA1851"
            specs["memory_type"] = "DDR5"
        elif "z790" in text or "b760" in text or "lga1700" in text:
            specs["socket"] = "LGA1700"
            specs["memory_type"] = "DDR4" if "ddr4" in text else "DDR5"
        elif "am4" in text or "b550" in text:
            specs["socket"] = "AM4"
            specs["memory_type"] = "DDR4"

        # Form Factor
        if "micro-atx" in text or "m-atx" in text or "matx" in text:
            specs["form_factor"] = "Micro-ATX"
        elif "mini-itx" in text or "itx" in text:
            specs["form_factor"] = "Mini-ITX"
        elif "e-atx" in text or "eatx" in text:
            specs["form_factor"] = "E-ATX"
        else:
            specs["form_factor"] = "ATX"

        return specs

    @staticmethod
    def normalize_ram(name: str, raw_specs: dict) -> dict:
        text = f"{name} {raw_specs}".lower()
        specs = {}

        specs["memory_type"] = "DDR4" if "ddr4" in text else "DDR5"

        # Speed (MHz)
        speed_match = re.search(r"(\d{4})\s?mhz", text)
        if speed_match:
            specs["speed_mhz"] = int(speed_match.group(1))

        # Capacity (GB)
        cap_match = re.search(r"(\d+)\s?gb", text)
        if cap_match:
            specs["capacity_gb"] = int(cap_match.group(1))

        return specs

    @staticmethod
    def normalize_psu(name: str, raw_specs: dict) -> dict:
        text = f"{name} {raw_specs}".lower()
        specs = {}

        # Wattage
        watt_match = re.search(r"(\d{3,4})\s?w\b", text)
        if watt_match:
            specs["wattage"] = int(watt_match.group(1))

        # Rating
        if "platinum" in text:
            specs["efficiency_rating"] = "80+ Platinum"
        elif "gold" in text:
            specs["efficiency_rating"] = "80+ Gold"
        elif "bronze" in text:
            specs["efficiency_rating"] = "80+ Bronze"

        return specs

    @staticmethod
    def normalize_cabinet(name: str, raw_specs: dict) -> dict:
        text = f"{name} {raw_specs}".lower()
        specs = {}

        if "full tower" in text or "super tower" in text:
            specs["form_factor"] = "Full Tower"
        elif "mini-itx" in text or "itx" in text:
            specs["form_factor"] = "Mini-ITX"
        elif "micro-atx" in text or "matx" in text:
            specs["form_factor"] = "Micro-ATX"
        else:
            specs["form_factor"] = "Mid Tower"

        return specs

    @staticmethod
    def normalize_cooler(name: str, raw_specs: dict) -> dict:
        text = f"{name} {raw_specs}".lower()
        specs = {}
        if "liquid" in text or "aio" in text or "360mm" in text or "240mm" in text or "420mm" in text or "120mm" in text:
            specs["cooler_type"] = "Liquid"
        else:
            specs["cooler_type"] = "Air"

        if "360mm" in text or "360" in text:
            specs["radiator_size_mm"] = 360
        elif "240mm" in text or "240" in text:
            specs["radiator_size_mm"] = 240
        elif "420mm" in text or "420" in text:
            specs["radiator_size_mm"] = 420
        elif "120mm" in text or "120" in text:
            specs["radiator_size_mm"] = 120
        return specs

    @staticmethod
    def normalize_ssd(name: str, raw_specs: dict) -> dict:
        text = f"{name} {raw_specs}".lower()
        specs = {}
        if "nvme" in text or "m.2" in text or "gen4" in text or "gen5" in text or "gen3" in text:
            specs["interface"] = "M.2 NVMe"
        elif "sata" in text or "hdd" in text or "hard drive" in text:
            specs["interface"] = "SATA"

        cap_match = re.search(r"(\d+)\s?(tb|gb)", text)
        if cap_match:
            val = int(cap_match.group(1))
            unit = cap_match.group(2)
            specs["capacity_gb"] = val * 1000 if unit == "tb" else val
        return specs

    @staticmethod
    def normalize_monitor(name: str, raw_specs: dict) -> dict:
        text = f"{name} {raw_specs}".lower()
        specs = {}
        size_match = re.search(r"(\d{2}\.?\d?)\s?(inch|\"|-inch)", text)
        if size_match:
            specs["screen_size_inch"] = float(size_match.group(1))

        hz_match = re.search(r"(\d{2,3})\s?hz", text)
        if hz_match:
            specs["refresh_rate_hz"] = int(hz_match.group(1))

        if "4k" in text or "3840x2160" in text:
            specs["resolution"] = "3840x2160"
        elif "2k" in text or "qhd" in text or "2560x1440" in text or "1440p" in text:
            specs["resolution"] = "2560x1440"
        elif "fhd" in text or "1080p" in text or "1920x1080" in text:
            specs["resolution"] = "1920x1080"

        return specs
