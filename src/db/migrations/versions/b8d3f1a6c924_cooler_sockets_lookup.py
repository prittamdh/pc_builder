"""cooler sockets for the most-listed coolers, looked up from spec sheets

Only 21 of 564 listed coolers had supported sockets, so the cooler/CPU check was
unverified on almost every build. AI recall was tried and rejected (it copied a
"typical" list, missed LGA1851, added sockets newer coolers dropped). These 81 models,
the most-listed without sockets, were looked up by hand on 2026-10-08 from maker spec
sheets or retailer spec tables that agree; where sources disagreed only the sockets
they share were kept. sockets_source records where each list came from.

Revision ID: b8d3f1a6c924
Revises: a7c2e9f4b118
Create Date: 2026-10-08 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8d3f1a6c924'
down_revision: Union[str, Sequence[str], None] = 'a7c2e9f4b118'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# canonical_id: (sockets in CPU spellings, source)
SOCKETS = {
    'cooler:arctic:liquid_freezer_iii_pro': ('LGA1700,LGA1851,AM4,AM5', 'retailers (memoryc, shi); series page omits AM4'),
    'cooler:arctic:liquid_freezer_iii_pro_240': ('LGA1700,LGA1851,AM4,AM5', 'same series'),
    'cooler:arctic:liquid_freezer_iii_pro_280': ('LGA1700,LGA1851,AM4,AM5', 'same series'),
    'cooler:arctic:liquid_freezer_iii_pro_360': ('LGA1700,LGA1851,AM4,AM5', 'same series'),
    'cooler:arctic:liquid_freezer_iii_pro_420': ('LGA1700,LGA1851,AM4,AM5', 'same series'),
    'cooler:arctic:liquid_freezer_iii_420': ('LGA1700,LGA1851,AM4,AM5', 'LF III series listing'),
    'cooler:msi:mag_coreliquid_a13': ('LGA1700,LGA1851,AM4,AM5', 'memoryexpress, buildcores, dateks'),
    'cooler:arctic:freezer_36': ('LGA1700,LGA1851,AM4,AM5', 'scan.co.uk, Arctic copy'),
    'cooler:arctic:freezer_36_co': ('LGA1700,LGA1851,AM4,AM5', 'Freezer 36 family'),
    'cooler:arctic:freezer_36_a-rgb': ('LGA1700,LGA1851,AM4,AM5', 'Freezer 36 family'),
    'cooler:arctic:freezer_36_argb': ('LGA1700,LGA1851,AM4,AM5', 'Freezer 36 family'),
    'cooler:msi:mag_corefrozr_aa13': ('LGA1700,LGA1851,AM4,AM5', 'scan.co.uk, potent, alza'),
    'cooler:deepcool:le360_v2': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,LGA1851,AM4,AM5', 'paradigit, datek, pcinternational'),
    'cooler:deepcool:le240_v2': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,LGA1851,AM4,AM5', 'LE V2 family'),
    'cooler:cooler_master:hyper_212_3dhp': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'ldlc, pccasegear, adorama'),
    'cooler:cougar:poseidon_elite': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1366,LGA1700,LGA1851,AM2,AM3,AM4,AM5,FM1,FM2', 'alltron'),
    'cooler:cougar:poseidon_vistek': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1700,LGA1851,AM3,AM4,AM5,FM1,FM2', 'paradigit (Vistek ARGB 360)'),
    'cooler:cougar:poseidon_vistek_pro': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1366,LGA1700,LGA1851,AM2,AM3,AM4,AM5,FM1,FM2', 'kaufland spec table'),
    'cooler:thermaltake:ux400': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM2,AM2+,AM3,AM3+,AM4,AM5,FM1,FM2', 'Thermaltake data sheet rev A Dec 2024'),
    'cooler:cooler_master:masterliquid_atmos_ii': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'paradigit (LCD/VRM/Pixel variants)'),
    'cooler:cooler_master:masterliquid_atmos_ii_360_lcd': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'Atmos II family'),
    'cooler:cooler_master:masterliquid_atmos_ii_lcd': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'Atmos II family'),
    'cooler:cooler_master:master_liquid_atmos_ii': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'Atmos II family'),
    'cooler:deepcool:lm360': ('LGA1150,LGA1151,LGA1155,LGA1700,LGA1851,AM4,AM5', 'paradigit, bsl-it (one adds LGA1200; left out)'),
    'cooler:deepcool:ld360': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,AM4,AM5', 'galaxus, dateks'),
    'cooler:deepcool:ld240': ('LGA1700,LGA1851,AM4,AM5', 'paradigit; cyberpuerta adds 115x/1200 without 1851 (sources disagree, kept common part)'),
    'cooler:deepcool:lt360': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,AM4,AM5', 'arvutitark (Threadripper claim not repeated elsewhere, left out)'),
    'cooler:deepcool:lt240': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,AM4,AM5', 'cyberpuerta, jib'),
    'cooler:msi:mpg_coreliquid_p13': ('LGA1700,LGA1851,AM4,AM5', 'guru3d review, pccasegear'),
    'cooler:msi:mag_coreliquid_a15': ('LGA1700,LGA1851,AM4,AM5', 'buildcores, canadacomputers, shi'),
    'cooler:corsair:nautilus_240_rs': ('LGA1700,LGA1851,AM4,AM5', 'scan, memoryexpress'),
    'cooler:corsair:nautilus_360_rs': ('LGA1700,LGA1851,AM4,AM5', 'Nautilus RS series (pccasegear)'),
    'cooler:corsair:nautilus_rs': ('LGA1700,LGA1851,AM4,AM5', 'Nautilus RS series'),
    'cooler:corsair:nautilus_360_rs_lcd': ('LGA1700,LGA1851,AM4,AM5', 'Nautilus RS series'),
    'cooler:corsair:nautilus_240_rs_lcd': ('LGA1700,LGA1851,AM4,AM5', 'Nautilus RS series'),
    'cooler:cooler_master:masterliquid_360l_core': ('LGA1200,LGA1700,LGA1851,AM4,AM5', 'retailer listing MLW-D36M-A18PZ-R1'),
    'cooler:cooler_master:masterliquid_240l_core': ('LGA1200,LGA1700,LGA1851,AM4,AM5', 'retailer listing MLW-D24M-A18PZ-RW'),
    'cooler:cooler_master:masterliquid_240_core_ii': ('LGA1150,LGA1151,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'paradigit'),
    'cooler:cooler_master:masterliquid_360_core_ii': ('LGA1150,LGA1151,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'Core II family (paradigit 240)'),
    'cooler:cooler_master:hyper_212_spectrum_v3': ('LGA1200,LGA1700,LGA1851,AM4,AM5', 'retailers; 2023 launch also lists 115X (left out)'),
    'cooler:cooler_master:hyper_620s': ('LGA1200,LGA1700,LGA1851,AM4,AM5', 'retailers, vortez launch article'),
    'cooler:cooler_master:hyper_612_apex': ('LGA1700,LGA1851,AM4,AM5', 'retailers (distributor adds 115x/1200; left out)'),
    'cooler:cooler_master:masterliquid_core_nex_360': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'pbtech spec sheet, dcs'),
    'cooler:cooler_master:masterliquid_core_nex_240': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'Core Nex family'),
    'cooler:cooler_master:masterliquid_core_nex_digital': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'pbtech (Core Nex Digital)'),
    'cooler:noctua:nh-d15_g2': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'anandtech review table, retailers'),
    'cooler:noctua:nh-d9_tr5-sp6': ('SP6,sTR5', 'Noctua spec, ldlc, pccasegear'),
    'cooler:thermaltake:ux200_se': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,AM2,AM2+,AM3,AM3+,AM4,FM1,FM2', 'shi, owl360 (AM5 disputed, left out)'),
    'cooler:thermaltake:th360_v2_ultra': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA2011,LGA2066,AM2,AM3,AM4,AM5,FM1,FM2', 'shi listings'),
    'cooler:thermaltake:magfloe_360_ultra': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'proshop, inception, shi'),
    'cooler:thermaltake:minecube_360_ultra': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4', 'shi (AM5 not listed)'),
    'cooler:deepcool:ak400_digital_se': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,LGA1851,AM4,AM5', 'retailer listing'),
    'cooler:deepcool:ak400_g2': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'teqex, alza'),
    'cooler:deepcool:ag400_g2': ('LGA1700,LGA1851,AM4,AM5', 'alza (two listings)'),
    'cooler:thermaltake:th360_v3': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1366,LGA1700,LGA1851,LGA2011,LGA2066,AM4,AM5', 'memoryc, comparateur-gamer'),
    'cooler:thermaltake:th360_v3_ultra': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,LGA1851,AM4,AM5', 'cyberpuerta'),
    'cooler:thermaltake:la360-s': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,LGA2011,LGA2066,AM4,AM5', 'mdcomputers, alza (AM3 disputed, left out)'),
    'cooler:thermaltake:la240-s': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,LGA2011,LGA2066,AM4,AM5', 'advice.co.th, alza'),
    'cooler:thermaltake:la360': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,LGA2011,LGA2066,AM4,AM5', 'alza (LA360)'),
    'cooler:cooler_master:hyper_212_halo': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,AM4,AM5', 'retailer listings (LGA1851 only on Black variant listing; left out)'),
    'cooler:cooler_master:v4_alpha_3dhp': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'channel listing, noticias3d review'),
    'cooler:deepcool:mystique_360': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,AM4,AM5', 'paradigit, dateks, proshop, ple (box.co.uk adds 1851)'),
    'cooler:gigabyte:gaming_360': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,AM4,AM5', 'box.co.uk, ple, microcenterindia'),
    'cooler:asus:prime_lc_360': ('LGA1200,LGA1700,LGA1851,AM4,AM5', 'shi part listing (115x on some listings only)'),
    'cooler:antec:vortex_lum': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,LGA2011,LGA2066,AM3,AM4,AM5', 'scan, datek, teqex'),
    'cooler:ant_esports:ice_chroma_360': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,AM2,AM3,AM4,AM5', 'mdcomputers (white and black listings, common part)'),
    'cooler:ant_esports:ice_chroma_240': ('LGA1151,LGA1200,LGA1700,AM3,AM4,AM5', 'mdcomputers headline (detail table longer; kept the common part)'),
    'cooler:ant_esports:ice-360': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1366,LGA1700,LGA2011,LGA2066,AM2,AM2+,AM3,AM3+,AM4,AM5,FM1,FM2', 'mdcomputers spec table'),
    'cooler:thermaltake:astria_600': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA2011,LGA2066,AM4,AM5', 'shi, pccomponentes (1851 on one listing only)'),
    'cooler:arctic:alpine_23_co': ('AM4,AM5', 'dateks, avoira, directcomputers (AMD-only cooler)'),
    'cooler:deepcool:ak400': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,AM4', 'ldlc, memoryexpress (AM5 disputed; covered by the AM4 mount rule)'),
    'cooler:deepcool:ak700_vc': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,LGA1851,AM4,AM5', 'Deepcool press release 2026'),
    'cooler:montech:hyperflow_360': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA1851,LGA2011,AM3,AM4,AM5', 'paradigit (Hyper Flow 360 ARGB), datafox'),
    'cooler:lian_li:hydroshift_ii_lcd-s': ('LGA1700,LGA1851,AM4,AM5', 'memoryexpress spec sheet, galaxus, Lian Li copy'),
    'cooler:xigmatek:liquid_killer_x_240': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA2011,LGA2066,AM3,AM4', 'startech, ryans (AM5/TR4 disputed)'),
    'cooler:cooler_master:masterliquid_pl360_flux': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,LGA2011,LGA2066,AM2,AM3,AM4,FM1,FM2', 'ldlc, channelonline (AM5/1851 only on some listings)'),
    'cooler:noctua:nh-d15': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1700,AM4,AM5', 'retailer spec sheets (SecuFirm2, NM-i17xx kit)'),
    'cooler:thermaltake:th360-s_v3': ('LGA1150,LGA1151,LGA1155,LGA1156,LGA1200,LGA1366,LGA1700,LGA1851,LGA2011,LGA2066,AM3,AM3+,AM4,AM5', 'cyberpuerta, comparateur-gamer'),
    'cooler:deepcool:assassin_iv': ('LGA1150,LGA1151,LGA1155,LGA1200,LGA1700,LGA2011,LGA2066,AM4,AM5', 'techpowerup, ocinside review'),
    'cooler:deepcool:lt360_vision': ('LGA1150,LGA1151,LGA1155,LGA1700,LGA1851,AM4,AM5', 'paradigit'),
    'cooler:deepcool:spartacus_360': ('LGA1700,LGA1851,AM4,AM5', 'grosbill, cowcotland'),
}


def upgrade() -> None:
    op.add_column("cooler_specs", sa.Column("sockets_source", sa.String(length=255), nullable=True))
    update = sa.text(
        "UPDATE cooler_specs SET supported_sockets = :s, sockets_source = :src "
        "WHERE canonical_id = :cid AND supported_sockets IS NULL")
    bind = op.get_bind()
    n = 0
    for cid, (sockets, src) in SOCKETS.items():
        n += bind.execute(update, {"s": sockets, "src": "lookup 2026-10-08: " + src, "cid": cid}).rowcount
    print(f"[cooler_sockets_lookup] {n} of {len(SOCKETS)} coolers filled")


def downgrade() -> None:
    op.execute("UPDATE cooler_specs SET supported_sockets = NULL "
               "WHERE sockets_source LIKE 'lookup 2026-10-08:%'")
    op.drop_column("cooler_specs", "sockets_source")
