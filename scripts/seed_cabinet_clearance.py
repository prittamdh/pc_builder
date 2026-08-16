"""
Seed cabinet clearance specs for the most-listed cases from manufacturer spec sheets.

No bulk dataset of case clearances exists (checked GitHub, Kaggle and the case
configurator sites - all are interactive tools without exports), and these numbers are
essentially never in retailer titles. So the highest-listed cases are filled from
manufacturer product sheets and reviews, verified 2026-08-16, and everything else stays
null rather than estimated: a guessed clearance would confidently green-light a card
that does not physically fit.
"""
import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select
from db.session import SessionLocal
from db.models.canonical_part import CanonicalPart
from db.models.category_specs import CabinetSpecs

# canonical_id -> (max_gpu_length_mm, max_cooler_height_mm, source note)
# Conservative figures used where a spec sheet gives a range (e.g. Meshify 2's 470mm
# open layout vs 445mm with a front fan installed): the smaller number is what a real
# build has to satisfy.
VERIFIED = {
    "case:lian_li:black:a3":  (415, 165, "Lian Li A3-mATX product page"),
    "case:lian_li:white:a3":  (415, 165, "Lian Li A3-mATX product page"),
    "case:fractal_design:black:meshify_2": (445, 185, "Fractal Design Meshify 2 product sheet (445mm with front fan fitted)"),
    "case:corsair:3200d_rs_argb": (375, 165, "Corsair 3200D RS product page (375mm with front fans)"),
}


def main() -> None:
    with SessionLocal() as session:
        updated = 0
        for cid, (gpu_len, cooler_h, source) in VERIFIED.items():
            cp = session.scalar(select(CanonicalPart).where(CanonicalPart.canonical_id == cid))
            if cp is None:
                print(f"  SKIP (no canonical part): {cid}")
                continue

            row = session.scalar(select(CabinetSpecs).where(CabinetSpecs.canonical_id == cid))
            if row is None:
                row = CabinetSpecs(canonical_id=cid, status="pending")
                session.add(row)

            row.max_gpu_length_mm = gpu_len
            row.max_cooler_height_mm = cooler_h
            row.confidence = "high"
            row.notes = f"Web-verified 2026-08-16 from {source}."
            row.status = "ok"
            updated += 1
            print(f"  {cid}: GPU<={gpu_len}mm, cooler<={cooler_h}mm")

        session.commit()
        total = session.scalar(select(CabinetSpecs).where(CabinetSpecs.max_gpu_length_mm.isnot(None)).with_only_columns(CabinetSpecs.canonical_id))
        have = len(list(session.scalars(select(CabinetSpecs).where(CabinetSpecs.max_gpu_length_mm.isnot(None)))))
        allc = len(list(session.scalars(select(CabinetSpecs))))
        print(f"\n  Updated: {updated}")
        print(f"  Coverage: {have}/{allc} cabinets now have max_gpu_length_mm")


if __name__ == "__main__":
    main()
