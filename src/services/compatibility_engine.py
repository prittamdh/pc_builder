"""
Strict PC Hardware Compatibility Engine.
Validates normalized specifications across category tables (cpu_specs, motherboard_specs, etc.).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.category_specs import (
    CabinetSpecs,
    CoolerSpecs,
    CPUSpecs,
    GPUSpecs,
    MotherboardSpecs,
    PSUSpecs,
    RAMSpecs,
    SSDSpecs,
)
from db.models.product import Product
from domain.builder import CompatibilityWarning


class CompatibilityEngine:
    def __init__(self, session: Session):
        self.session = session

    def validate_build(self, product_ids: list[int]) -> tuple[bool, list[CompatibilityWarning], int]:
        if not product_ids:
            return True, [], 0

        warnings: list[CompatibilityWarning] = []
        compatible = True
        estimated_wattage = 0

        # Query normalized category specs
        cpus = list(self.session.scalars(select(CPUSpecs).where(CPUSpecs.product_id.in_(product_ids))))
        mobs = list(self.session.scalars(select(MotherboardSpecs).where(MotherboardSpecs.product_id.in_(product_ids))))
        rams = list(self.session.scalars(select(RAMSpecs).where(RAMSpecs.product_id.in_(product_ids))))
        gpus = list(self.session.scalars(select(GPUSpecs).where(GPUSpecs.product_id.in_(product_ids))))
        psus = list(self.session.scalars(select(PSUSpecs).where(PSUSpecs.product_id.in_(product_ids))))
        cases = list(self.session.scalars(select(CabinetSpecs).where(CabinetSpecs.product_id.in_(product_ids))))
        coolers = list(self.session.scalars(select(CoolerSpecs).where(CoolerSpecs.product_id.in_(product_ids))))

        # 1. CPU ↔ Motherboard (Socket Match)
        if cpus and mobs:
            for cpu in cpus:
                for mob in mobs:
                    if cpu.socket and mob.socket and cpu.socket.upper() != mob.socket.upper():
                        compatible = False
                        warnings.append(
                            CompatibilityWarning(
                                level="error",
                                message=f"Socket Mismatch: CPU socket ({cpu.socket}) is incompatible with Motherboard socket ({mob.socket}).",
                            )
                        )

        # 2. Motherboard ↔ RAM (Memory Type Match)
        if mobs and rams:
            for mob in mobs:
                for ram in rams:
                    if mob.memory_type and ram.memory_type and mob.memory_type.upper() != ram.memory_type.upper():
                        compatible = False
                        warnings.append(
                            CompatibilityWarning(
                                level="error",
                                message=f"RAM Standard Mismatch: Motherboard supports {mob.memory_type}, but selected RAM is {ram.memory_type}.",
                            )
                        )

        # 3. GPU & CPU Estimated Wattage vs PSU
        cpu_watt = sum(c.tdp or 120 for c in cpus)
        gpu_watt = sum(g.tdp or 250 for g in gpus)
        estimated_wattage = cpu_watt + gpu_watt + 50  # 50W base system draw

        if gpus and psus:
            rec_psu = max(g.recommended_psu or 650 for g in gpus)
            psu_capacity = max(p.wattage or 600 for p in psus)
            if psu_capacity < rec_psu:
                warnings.append(
                    CompatibilityWarning(
                        level="warning",
                        message=f"PSU Capacity Warning: GPU recommends at least {rec_psu}W PSU, but selected PSU is {psu_capacity}W.",
                    )
                )

        # 4. GPU ↔ Cabinet (Length Clearance)
        if gpus and cases:
            for gpu in gpus:
                for case in cases:
                    if gpu.length_mm and case.max_gpu_length_mm and gpu.length_mm > case.max_gpu_length_mm:
                        compatible = False
                        warnings.append(
                            CompatibilityWarning(
                                level="error",
                                message=f"GPU Clearance Error: GPU length ({gpu.length_mm}mm) exceeds Cabinet max clearance ({case.max_gpu_length_mm}mm).",
                            )
                        )

        # 5. Cooler ↔ Socket
        if coolers and cpus:
            for cooler in coolers:
                for cpu in cpus:
                    if cooler.supported_sockets and cpu.socket:
                        if cpu.socket.upper() not in cooler.supported_sockets.upper():
                            warnings.append(
                                CompatibilityWarning(
                                    level="warning",
                                    message=f"Cooler Mounting Check: Verify cooler mounting kit supports {cpu.socket} socket.",
                                )
                            )

        return compatible, warnings, estimated_wattage
