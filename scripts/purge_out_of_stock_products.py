"""
Script to purge all out-of-stock products (in_stock=False) and associated records
from PostgreSQL across all stores.
"""
from sqlalchemy import text
from db.session import SessionLocal


def purge_out_of_stock():
    with SessionLocal() as session:
        print("Purging out-of-stock products and associated records from PostgreSQL...")

        spec_tables = [
            "cpu_specs", "gpu_specs", "motherboard_specs", "ram_specs",
            "ssd_specs", "psu_specs", "cabinet_specs", "cooler_specs", "monitor_specs"
        ]
        for tbl in spec_tables:
            res = session.execute(text(f"DELETE FROM {tbl} WHERE product_id IN (SELECT id FROM products WHERE in_stock = false)"))
            print(f"  Deleted {res.rowcount} out-of-stock rows from '{tbl}'.")

        pt_res = session.execute(text("DELETE FROM product_targets WHERE product_id IN (SELECT id FROM products WHERE in_stock = false)"))
        print(f"  Deleted {pt_res.rowcount} out-of-stock rows from 'product_targets'.")

        ph_res = session.execute(text("DELETE FROM price_history WHERE product_id IN (SELECT id FROM products WHERE in_stock = false)"))
        print(f"  Deleted {ph_res.rowcount} out-of-stock rows from 'price_history'.")

        p_res = session.execute(text("DELETE FROM products WHERE in_stock = false"))
        print(f"  Deleted {p_res.rowcount} out-of-stock products from 'products'.")

        session.commit()
        print("=" * 80)
        print("OUT-OF-STOCK PURGE COMPLETE! Only 100% in-stock products remain.")


if __name__ == "__main__":
    purge_out_of_stock()
