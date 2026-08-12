"""
Empirical schema update script to apply Phase 1-2 corrections to PostgreSQL.
- Drops specs column from canonical_parts
- Adds canonical_id FK + index to all 9 category spec tables
- Ensures alembic_version is updated cleanly
"""
from db.session import SessionLocal
from sqlalchemy import text


def apply_schema_corrections():
    with SessionLocal() as session:
        print("=" * 80)
        print("APPLYING CANONICAL SCHEMA CORRECTIONS TO POSTGRESQL")
        print("=" * 80)

        # 1. Ensure chipset_specs table exists
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS chipset_specs (
                chipset_id VARCHAR(255) PRIMARY KEY,
                category VARCHAR(100) NOT NULL,
                specs JSONB NOT NULL,
                source VARCHAR(100) NOT NULL DEFAULT 'manual',
                verified BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS ix_chipset_specs_category ON chipset_specs(category);
        """))

        # 2. Ensure canonical_parts table exists without specs column
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS canonical_parts (
                canonical_id VARCHAR(255) PRIMARY KEY,
                category VARCHAR(100) NOT NULL,
                brand VARCHAR(255) NOT NULL,
                key_fields JSONB NOT NULL,
                chipset_id VARCHAR(255) REFERENCES chipset_specs(chipset_id) ON DELETE SET NULL,
                from_title JSONB NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'OK',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            ALTER TABLE canonical_parts DROP COLUMN IF EXISTS specs;
            CREATE INDEX IF NOT EXISTS ix_canonical_parts_category ON canonical_parts(category);
            CREATE INDEX IF NOT EXISTS ix_canonical_parts_brand ON canonical_parts(brand);
            CREATE INDEX IF NOT EXISTS ix_canonical_parts_chipset_id ON canonical_parts(chipset_id);
            CREATE INDEX IF NOT EXISTS ix_canonical_parts_status ON canonical_parts(status);
        """))

        # 3. Ensure products table has canonical_id column & index
        session.execute(text("""
            ALTER TABLE products ADD COLUMN IF NOT EXISTS canonical_id VARCHAR(255);
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_products_canonical_id'
                ) THEN
                    ALTER TABLE products ADD CONSTRAINT fk_products_canonical_id 
                    FOREIGN KEY (canonical_id) REFERENCES canonical_parts(canonical_id) ON DELETE SET NULL;
                END IF;
            END $$;
            CREATE INDEX IF NOT EXISTS ix_products_canonical_id ON products(canonical_id);
        """))

        # 4. Add canonical_id column + FK + index to all 9 category spec tables
        spec_tables = [
            'cpu_specs', 'gpu_specs', 'motherboard_specs', 'ram_specs',
            'ssd_specs', 'psu_specs', 'cabinet_specs', 'cooler_specs', 'monitor_specs'
        ]
        for tbl in spec_tables:
            session.execute(text(f"""
                ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS canonical_id VARCHAR(255);
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'fk_{tbl}_canonical_id'
                    ) THEN
                        ALTER TABLE {tbl} ADD CONSTRAINT fk_{tbl}_canonical_id 
                        FOREIGN KEY (canonical_id) REFERENCES canonical_parts(canonical_id) ON DELETE CASCADE;
                    END IF;
                END $$;
                CREATE INDEX IF NOT EXISTS ix_{tbl}_canonical_id ON {tbl}(canonical_id);
            """))

        # 5. Set alembic_version revision to a1b2c3d4e5f6
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
            DELETE FROM alembic_version;
            INSERT INTO alembic_version (version_num) VALUES ('a1b2c3d4e5f6');
        """))

        session.commit()
        print("\n[OK] Schema corrections applied cleanly to PostgreSQL!")
        print("=" * 80)


if __name__ == "__main__":
    apply_schema_corrections()
