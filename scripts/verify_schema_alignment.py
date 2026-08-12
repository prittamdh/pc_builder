"""
Verification script for schema architecture alignment and GPU canonical key builder fix.
"""
from sqlalchemy import text
from db.session import SessionLocal
from matching.canonical_key_builder import build_canonical_key, make_canonical_key_string


def verify_all():
    print("=" * 80)
    print("VERIFYING ARCHITECTURE ALIGNMENT & CANONICAL SCHEMA CORRECTIONS")
    print("=" * 80)

    with SessionLocal() as session:
        # 1. Inspect canonical_parts columns
        sql_cp_cols = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'canonical_parts';
        """)
        cp_cols = [r[0] for r in session.execute(sql_cp_cols).fetchall()]

        print("\n[1] CANONICAL_PARTS TABLE COLUMNS:")
        print(f"  Columns: {cp_cols}")
        assert "specs" not in cp_cols, "ERROR: 'specs' JSONB column still exists on canonical_parts!"
        assert "canonical_id" in cp_cols and "key_fields" in cp_cols and "from_title" in cp_cols, "ERROR: missing core columns on canonical_parts!"
        print("  [OK] Verified: canonical_parts is a thin identity table (specs column removed!).")

        # 2. Inspect 9 category spec tables for canonical_id column
        spec_tables = [
            'cpu_specs', 'gpu_specs', 'motherboard_specs', 'ram_specs',
            'ssd_specs', 'psu_specs', 'cabinet_specs', 'cooler_specs', 'monitor_specs'
        ]
        print("\n[2] RELATIONAL SPEC TABLES CANONICAL_ID FOREIGN KEYS:")
        for tbl in spec_tables:
            sql_spec_cols = text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{tbl}' AND column_name = 'canonical_id';
            """)
            has_col = bool(session.execute(sql_spec_cols).fetchall())
            print(f"  • {tbl:<20}: canonical_id column present = {has_col}")
            assert has_col, f"ERROR: '{tbl}' table is missing canonical_id column!"
        print("  [OK] Verified: All 9 category spec tables contain canonical_id FK!")

        # 3. Test GPU brand duplication stripping in build_canonical_key
        print("\n[3] GPU BRAND DUPLICATION STRIPPING TEST:")
        gpu_title = "MSI GeForce RTX 4070 Ti Super Gaming X Slim 16GB Graphics Card"
        key_dict = build_canonical_key(gpu_title, "GPU")
        key_str = make_canonical_key_string("GPU", key_dict)

        print(f"  Title: '{gpu_title}'")
        print(f"  Key Dict: {key_dict}")
        print(f"  Key String: '{key_str}'")

        assert key_dict["variant_model"] == "gaming x", f"Unexpected variant_model: {key_dict['variant_model']}"
        assert key_str == "gpu:msi:rtx_4070_ti_super:gaming_x", f"Unexpected key_str: {key_str}"
        print("  [OK] Verified: GPU variant_model strips duplicate brand token! Key: 'gpu:msi:rtx_4070_ti_super:gaming_x'")

    print("\n" + "=" * 80)
    print("ALL ARCHITECTURE & SCHEMA CORRECTIONS Empirically VERIFIED!")
    print("=" * 80)


if __name__ == "__main__":
    verify_all()
