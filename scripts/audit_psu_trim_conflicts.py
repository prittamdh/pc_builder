"""
Report canonical PSU groups whose key trim contradicts the trim in psu_specs.

The two come from independent evidence - the key trim is read off listing titles in
Stage 1, the spec trim is extracted in Stage 2 from the model name grounded in real
listing text - so a disagreement means one of them mis-read, and the group is suspect.

Read-only. It names conflicts for a human to judge; it never merges or rewrites, because
a conflict shows a group is wrong without showing which side is right.
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from db.session import SessionLocal
from db.models.category_specs import PSUSpecs
from matching.psu_identity import find_trim_conflicts


def main():
    with SessionLocal() as session:
        conflicts = find_trim_conflicts(session)
        print("=" * 80)
        print(f"PSU TRIM CONFLICTS: {len(conflicts)}")
        print("=" * 80)
        if not conflicts:
            print("  none - key trims and spec trims agree everywhere.")
            return

        specs = {
            r.canonical_id: r for r in session.scalars(
                select(PSUSpecs).where(
                    PSUSpecs.canonical_id.in_([c["canonical_id"] for c in conflicts])
                )
            )
        }
        for c in sorted(conflicts, key=lambda x: x["canonical_id"]):
            row = specs.get(c["canonical_id"])
            source = (row.llm_model if row and row.llm_model else "pre-LLM / unrecorded")
            print(f"  key={c['key_trim']:9} spec={c['spec_trim']:9} [{source[:28]:28}] {c['canonical_id']}")

        print("\n  Reading these: a group whose MODEL NAME already states a tier "
              "(\"Leadex III Gold\", MSI's \"GL\") carries the manufacturer's own marker,")
        print("  which outranks an inference on either side. Rows marked "
              "'pre-LLM / unrecorded' predate grounded extraction and are the likeliest wrong.")


if __name__ == "__main__":
    main()
