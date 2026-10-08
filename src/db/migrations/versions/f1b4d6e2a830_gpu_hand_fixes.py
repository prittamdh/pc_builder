"""GPU listings fixed by hand from their titles (owner review 2026-10-08)

Brand and chip the extractor missed (Nextron, EVM, Zebronics, reference AMD/NVIDIA
workstation cards, ASRock Arc), "AI Pro" dropped from R9700 card variants, and three
listings that are not graphics cards moved to their real category.

Revision ID: f1b4d6e2a830
Revises: e8a3c5d1f720
Create Date: 2026-10-08 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session

revision: str = 'f1b4d6e2a830'
down_revision: Union[str, Sequence[str], None] = 'e8a3c5d1f720'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The stored extraction is corrected, not just the key, so later re-keys keep it.
# Listing ids are production's; ids missing from a database update nothing.
SQL = r"""
UPDATE gpu_title_extractions e SET brand = v.brand, chipset = v.chip, variant = v.variant, status = 'ok', error = NULL,
       notes = 'set by hand from the title, owner review 2026-10-08'
FROM (VALUES
  (12374,'NVIDIA','RTX A400',''), (1940,'NVIDIA','RTX A400',''), (15241,'NVIDIA','RTX A400',''),
  (19844,'NVIDIA','RTX A1000',''),
  (15223,'HP','RTX A400','Mini Bracket'), (15224,'HP','RTX A1000','Mini Bracket'),
  (12459,'NVIDIA','RTX PRO 6000 Blackwell',''), (2042,'NVIDIA','RTX PRO 6000 Blackwell','Server Edition'),
  (12460,'NVIDIA','RTX PRO 2000 Blackwell',''), (20809,'NVIDIA','RTX PRO 2000 Blackwell',''),
  (19846,'PNY','RTX PRO 2000 Blackwell',''),
  (12461,'NVIDIA','RTX PRO 4000 Blackwell',''), (2035,'NVIDIA','RTX PRO 4000 Blackwell',''),
  (15999,'PNY','RTX PRO 4000 Blackwell','SFF'),
  (12462,'NVIDIA','RTX PRO 4500 Blackwell',''), (15226,'NVIDIA','RTX PRO 4500 Blackwell',''),
  (20816,'NVIDIA','RTX PRO 4500 Blackwell',''),
  (12463,'NVIDIA','RTX PRO 5000 Blackwell',''), (15232,'NVIDIA','RTX PRO 5000 Blackwell',''),
  (15993,'NVIDIA','RTX PRO 5000 Blackwell',''),
  (19143,'NVIDIA','RTX 2000 Ada',''), (20806,'NVIDIA','RTX 2000 Ada',''),
  (16024,'PNY','RTX 2000E Ada',''), (16028,'PNY','A800','Active'),
  (15230,'Nextron','GT 610',''), (15231,'Nextron','GT 730',''),
  (15989,'Nextron','RX 550',''), (17581,'Nextron','RX 550','Nforce'), (19764,'Nextron','RX 550',''),
  (20791,'Nextron','RX 550','Nforce'),
  (15990,'Nextron','RX 580',''), (16036,'Nextron','RX 580',''), (19763,'Nextron','RX 580',''),
  (20793,'Nextron','RX 580','Nforce'), (21160,'Nextron','RX 580',''),
  (16037,'Nextron','RX 6600','Nforce Legend'), (20178,'Nextron','RX 7600 XT',''),
  (20583,'Nextron','RX 7600 XT','Dual Fan'), (20582,'Nextron','RX 7600','Nforce'),
  (20794,'Nextron','GTX 1650',''), (20584,'Nextron','GTX 1650',''), (20585,'Nextron','GTX 1050 Ti','Dual Fan'),
  (16050,'Consistent','GT 730','Low Profile'),
  (16051,'EVM','GT 730',''), (16052,'EVM','GT 740',''), (16053,'EVM','GT 610',''),
  (20621,'Zebronics','GT 740',''), (20645,'Zebronics','GT 730',''), (20646,'Zebronics','GT 610',''),
  (18897,'MSI','GT 710',''),
  (19387,'ASRock','RX 9050','Challenger'),
  (20630,'ASRock','Arc B570','Challenger'), (20631,'ASRock','Arc B580','Steel Legend OC'),
  (21427,'ASRock','Arc B580','Challenger OC'), (21572,'ASRock','Arc B580','Challenger OC'),
  (19867,'AMD','Radeon PRO W5700',''), (19866,'AMD','Radeon PRO W6600',''),
  (19854,'AMD','Radeon PRO W7500',''), (19852,'AMD','Radeon PRO W7600',''),
  (19630,'AMD','Radeon PRO W7700',''), (16268,'AMD','Radeon PRO W7800',''),
  (19853,'AMD','Radeon PRO W7900',''),
  (16010,'Gigabyte','Radeon PRO W7800','AI TOP'), (16009,'Gigabyte','Radeon PRO W7900','Dual Slot AI TOP')
) AS v(pid, brand, chip, variant)
WHERE e.product_id = v.pid;

-- "AI Pro" is part of the R9700's name, not a card variant: Sapphire AI Pro -> Sapphire.
UPDATE gpu_title_extractions SET variant = btrim(regexp_replace(variant, 'ai[\s_]*pro', '', 'gi'))
WHERE variant ~* 'ai[\s_]*pro' AND (chipset ~* '9700' OR raw_title ~* 'R9700');

-- Not graphics cards: a WD external drive, Corsair RAM, a FirePro sync module.
UPDATE gpu_title_extractions SET status = 'not_gpu', notes = 'not a GPU, owner review 2026-10-08'
WHERE product_id IN (16267, 21663, 19855);
UPDATE products SET p_category = 'Storage', canonical_id = NULL WHERE id = 16267;
UPDATE products SET p_category = 'RAM', canonical_id = NULL WHERE id = 21663;
UPDATE products SET p_category = 'Accessories', canonical_id = NULL WHERE id = 19855;
"""


def upgrade() -> None:
    for statement in SQL.split(";"):
        if statement.strip() and not all(l.strip().startswith("--") or not l.strip() for l in statement.splitlines()):
            op.execute(statement)
    from matching.gpu_rekey import rekey_gpus

    session = Session(bind=op.get_bind())
    stats = rekey_gpus(session, dry_run=False)
    session.flush()
    print(f"[gpu_hand_fixes] {stats}")


def downgrade() -> None:
    # The old values were wrong; nothing correct to go back to.
    pass
