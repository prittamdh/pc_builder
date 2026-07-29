"""
Category specification models for PC Hardware.
Dedicated 1-to-1 tables storing normalized specs referencing products.id.
"""
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

try:
    from sqlalchemy.orm import Mapped, mapped_column
except ImportError:
    class Mapped:
        def __class_getitem__(cls, item):
            return Any
    from sqlalchemy import Column as mapped_column

from db.base import Base


class CPUSpecs(Base):
    __tablename__ = "cpu_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    socket: Mapped[str | None] = mapped_column(String(50), index=True)
    cores: Mapped[int | None] = mapped_column(Integer)
    threads: Mapped[int | None] = mapped_column(Integer)
    base_clock: Mapped[float | None] = mapped_column(Numeric(4, 2))
    boost_clock: Mapped[float | None] = mapped_column(Numeric(4, 2))
    tdp: Mapped[int | None] = mapped_column(Integer)
    integrated_graphics: Mapped[bool | None] = mapped_column(Boolean, default=False)
    architecture: Mapped[str | None] = mapped_column(String(100))


class GPUSpecs(Base):
    __tablename__ = "gpu_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    chipset: Mapped[str | None] = mapped_column(String(100), index=True)
    memory_size_gb: Mapped[int | None] = mapped_column(Integer)
    memory_type: Mapped[str | None] = mapped_column(String(20))
    tdp: Mapped[int | None] = mapped_column(Integer)
    recommended_psu: Mapped[int | None] = mapped_column(Integer)
    length_mm: Mapped[int | None] = mapped_column(Integer)
    slot_width: Mapped[float | None] = mapped_column(Numeric(3, 1))


class MotherboardSpecs(Base):
    __tablename__ = "motherboard_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    socket: Mapped[str | None] = mapped_column(String(50), index=True)
    chipset: Mapped[str | None] = mapped_column(String(50))
    form_factor: Mapped[str | None] = mapped_column(String(50))
    memory_type: Mapped[str | None] = mapped_column(String(20))
    memory_slots: Mapped[int | None] = mapped_column(Integer)
    max_memory_gb: Mapped[int | None] = mapped_column(Integer)
    m2_slots: Mapped[int | None] = mapped_column(Integer)


class RAMSpecs(Base):
    __tablename__ = "ram_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    memory_type: Mapped[str | None] = mapped_column(String(20), index=True)
    speed_mhz: Mapped[int | None] = mapped_column(Integer)
    capacity_gb: Mapped[int | None] = mapped_column(Integer)
    modules: Mapped[int | None] = mapped_column(Integer)
    latency_cl: Mapped[int | None] = mapped_column(Integer)


class SSDSpecs(Base):
    __tablename__ = "ssd_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    capacity_gb: Mapped[int | None] = mapped_column(Integer)
    form_factor: Mapped[str | None] = mapped_column(String(50))
    interface: Mapped[str | None] = mapped_column(String(50))
    read_speed_mbps: Mapped[int | None] = mapped_column(Integer)
    write_speed_mbps: Mapped[int | None] = mapped_column(Integer)


class PSUSpecs(Base):
    __tablename__ = "psu_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    wattage: Mapped[int | None] = mapped_column(Integer, index=True)
    efficiency_rating: Mapped[str | None] = mapped_column(String(50))
    modularity: Mapped[str | None] = mapped_column(String(50))
    form_factor: Mapped[str | None] = mapped_column(String(50))


class CabinetSpecs(Base):
    __tablename__ = "cabinet_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    form_factor: Mapped[str | None] = mapped_column(String(50))
    max_gpu_length_mm: Mapped[int | None] = mapped_column(Integer)
    max_cooler_height_mm: Mapped[int | None] = mapped_column(Integer)
    max_psu_length_mm: Mapped[int | None] = mapped_column(Integer)


class CoolerSpecs(Base):
    __tablename__ = "cooler_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    cooler_type: Mapped[str | None] = mapped_column(String(50))
    radiator_size_mm: Mapped[int | None] = mapped_column(Integer)
    fan_size_mm: Mapped[int | None] = mapped_column(Integer)
    supported_sockets: Mapped[str | None] = mapped_column(String(255))
    tdp_rating: Mapped[int | None] = mapped_column(Integer)


class MonitorSpecs(Base):
    __tablename__ = "monitor_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    screen_size_inch: Mapped[float | None] = mapped_column(Numeric(4, 1))
    resolution: Mapped[str | None] = mapped_column(String(50))
    refresh_rate_hz: Mapped[int | None] = mapped_column(Integer)
    panel_type: Mapped[str | None] = mapped_column(String(20))
    response_time_ms: Mapped[float | None] = mapped_column(Numeric(3, 1))
