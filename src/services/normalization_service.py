"""
Normalization Service.
Classifies product categories, normalizes specifications, and populates dedicated category spec tables.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.category_specs import (
    CabinetSpecs,
    CoolerSpecs,
    CPUSpecs,
    GPUSpecs,
    MonitorSpecs,
    MotherboardSpecs,
    PSUSpecs,
    RAMSpecs,
    SSDSpecs,
)
from db.models.product import Product
from matching.category_classifier import CategoryClassifier
from matching.spec_normalizer import SpecNormalizer


class NormalizationService:
    def __init__(self, session: Session):
        self.session = session

    def normalize_product(self, product: Product) -> str:
        cat = CategoryClassifier.classify(
            name=product.name,
            category_raw=product.category,
            url=product.product_url,
        )

        if product.category != cat:
            product.category = cat
            self.session.flush()

        raw_specs = product.specifications or {}

        if cat == "CPU":
            norm = SpecNormalizer.normalize_cpu(product.name, raw_specs)
            self._upsert_specs(CPUSpecs, product.id, norm)
        elif cat == "GPU":
            norm = SpecNormalizer.normalize_gpu(product.name, raw_specs)
            self._upsert_specs(GPUSpecs, product.id, norm)
        elif cat == "Motherboard":
            norm = SpecNormalizer.normalize_motherboard(product.name, raw_specs)
            self._upsert_specs(MotherboardSpecs, product.id, norm)
        elif cat == "RAM":
            norm = SpecNormalizer.normalize_ram(product.name, raw_specs)
            self._upsert_specs(RAMSpecs, product.id, norm)
        elif cat == "PSU":
            norm = SpecNormalizer.normalize_psu(product.name, raw_specs)
            self._upsert_specs(PSUSpecs, product.id, norm)
        elif cat == "Cabinet":
            norm = SpecNormalizer.normalize_cabinet(product.name, raw_specs)
            self._upsert_specs(CabinetSpecs, product.id, norm)

        self.session.commit()
        return cat

    def _upsert_specs(self, model_cls, product_id: int, norm_dict: dict):
        if not norm_dict:
            return

        stmt = select(model_cls).where(model_cls.product_id == product_id)
        db_spec = self.session.scalar(stmt)

        if db_spec is None:
            db_spec = model_cls(product_id=product_id, **norm_dict)
            self.session.add(db_spec)
        else:
            for k, v in norm_dict.items():
                setattr(db_spec, k, v)

        self.session.flush()

    def normalize_all_unclassified(self, limit: int = 100) -> int:
        stmt = select(Product).limit(limit)
        products = list(self.session.scalars(stmt))

        count = 0
        for p in products:
            self.normalize_product(p)
            count += 1

        return count
