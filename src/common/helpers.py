"""
Common helper functions.
"""

from pathlib import Path

import yaml

from configs.settings import PROJECT_ROOT


_SITE_CONFIG = None


def load_sites_config() -> dict:
    """
    Load all site configurations from sites.yaml.
    """

    global _SITE_CONFIG

    if _SITE_CONFIG is None:
        config_path = PROJECT_ROOT / "src" / "configs" / "sites.yaml"

        with open(config_path, "r", encoding="utf-8") as file:
            _SITE_CONFIG = yaml.safe_load(file)

    return _SITE_CONFIG


def get_site_config(site: str) -> dict:
    """
    Return configuration for a specific site.

    Example:
        get_site_config("mdcomputers")
    """

    config = load_sites_config()

    if site not in config:
        raise KeyError(f"Unknown site: {site}")

    return config[site]