"""
Configuration manager.
"""

from pathlib import Path

import yaml

from configs.settings import PROJECT_ROOT


class Config:
    _sites = None

    @classmethod
    def sites(cls) -> dict:
        if cls._sites is None:
            config_file = (
                PROJECT_ROOT
                / "src"
                / "configs"
                / "sites.yaml"
            )

            with open(config_file, "r", encoding="utf-8") as f:
                cls._sites = yaml.safe_load(f)

        return cls._sites

    @classmethod
    def site(cls, site_name: str) -> dict:
        return cls.sites()[site_name]