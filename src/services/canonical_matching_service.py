"""
Experimental Canonical Matching Service.
Utilizes scripts/normalize.py, scripts/schemas.py, and scripts/match.py to group raw store listings
into canonical products and store listings in separate experimental tables (canonical_products_test, store_listings_test).
"""
import sys
from pathlib import Path
import json

# Ensure scripts directory is on sys.path to import normalize, schemas, match
scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from normalize import normalize_title
from schemas import extract_attributes
from match import match_listings, Listing, MatchResult

from sqlalchemy.orm import Session
from sqlalchemy import text


class CanonicalMatchingService:
    def __init__(self, session: Session):
        self.session = session
        self._ensure_tables_exist()

    def _ensure_tables_exist(self):
        """Create experimental test tables canonical_products_test and store_listings_test if they don't exist."""
        sql = """
        CREATE TABLE IF NOT EXISTS canonical_products_test (
            id SERIAL PRIMARY KEY,
            canonical_key TEXT,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            attributes JSONB,
            needs_review BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
        );

        CREATE TABLE IF NOT EXISTS store_listings_test (
            id SERIAL PRIMARY KEY,
            canonical_product_id INT REFERENCES canonical_products_test(id) ON DELETE CASCADE,
            product_id INT,
            store_name TEXT,
            raw_title TEXT NOT NULL,
            normalized_title TEXT,
            price NUMERIC(12, 2),
            product_url TEXT
        );
        """
        self.session.execute(text(sql))
        self.session.commit()

    def run_experimental_matching(self) -> dict:
        """
        Loads all active products from PostgreSQL, runs match_listings(),
        and populates canonical_products_test & store_listings_test.
        """
        print("=" * 80)
        print("RUNNING EXPERIMENTAL CANONICAL MATCHING PIPELINE OVER 10-STORE DATA")
        print("=" * 80)

        # 1. Fetch raw products from database
        query = text("""
            SELECT p.id, s.display_name AS store_name, p.name AS raw_title, 
                   COALESCE(p.p_category, p.category) AS category, p.current_price, p.product_url, p.specifications
            FROM products p
            JOIN stores s ON p.sid = s.id
            WHERE p.in_stock = TRUE;
        """)
        rows = self.session.execute(query).fetchall()
        print(f"Loaded {len(rows)} in-stock products for canonical grouping...")

        listings: list[Listing] = []
        product_map: dict[str, int] = {}  # (raw_title + store_name) -> product_id

        for r in rows:
            pid, store_name, raw_title, category, price, product_url, specs = r
            if not category or not raw_title:
                continue

            # Standardize category key to match schemas.py expected keys (cpu, gpu, ram, storage, psu)
            cat_key = category.lower().strip()
            if cat_key in ("cpu", "processor"):
                cat_key = "cpu"
            elif cat_key in ("gpu", "graphics card"):
                cat_key = "gpu"
            elif cat_key in ("ram", "desktop ram", "laptop ram"):
                cat_key = "ram"
            elif cat_key in ("storage", "ssd", "hdd", "nvme ssd", "m.2 nvme ssd", "sata ssd"):
                cat_key = "storage"
            elif cat_key in ("power supply", "psu", "smps"):
                cat_key = "psu"
            else:
                continue  # Skip categories not currently covered by schemas.py extractors

            specs_dict = specs if isinstance(specs, dict) else {}
            listing = Listing(
                store_id=store_name,
                raw_title=raw_title,
                category=cat_key,
                price=float(price) if price else 0.0,
                url=product_url or "",
                specs=specs_dict
            )
            listings.append(listing)
            product_map[f"{store_name}::{raw_title}"] = pid

        # 2. Run match_listings() from scripts/match.py
        match_results: list[MatchResult] = match_listings(listings)
        print(f"Generated {len(match_results)} canonical match groups and review items!")

        # 3. Truncate test tables
        self.session.execute(text("TRUNCATE TABLE store_listings_test RESTART IDENTITY CASCADE;"))
        self.session.execute(text("TRUNCATE TABLE canonical_products_test RESTART IDENTITY CASCADE;"))
        self.session.commit()

        # 4. Insert grouped canonical results into test tables
        canonical_count = 0
        listing_count = 0
        review_count = 0

        for match in match_results:
            key_str = " | ".join(filter(None, [str(k) for k in match.canonical_key])) if match.canonical_key else "REVIEW_QUEUE"
            
            # Form clean human-readable canonical product title from attributes or first listing
            first_title = match.listings[0].raw_title if match.listings else "Canonical Product"
            attrs = match.attributes or {}
            brand = (attrs.get("brand") or "").upper()
            model = attrs.get("model") or ""
            c_name = f"{brand} {model}".strip() if (brand and model) else first_title

            # Insert Canonical Product
            res = self.session.execute(text("""
                INSERT INTO canonical_products_test (canonical_key, category, name, attributes, needs_review)
                VALUES (:key, :category, :name, :attrs, :needs_review)
                RETURNING id;
            """), {
                "key": key_str,
                "category": match.category,
                "name": c_name,
                "attrs": json.dumps(match.attributes),
                "needs_review": match.needs_review
            })
            canonical_id = res.fetchone()[0]
            canonical_count += 1
            if match.needs_review:
                review_count += 1

            # Insert Listings
            for lst in match.listings:
                orig_pid = product_map.get(f"{lst.store_id}::{lst.raw_title}")
                norm_t = normalize_title(lst.raw_title)

                self.session.execute(text("""
                    INSERT INTO store_listings_test (canonical_product_id, product_id, store_name, raw_title, normalized_title, price, product_url)
                    VALUES (:cid, :pid, :store_name, :raw_title, :norm_title, :price, :url);
                """), {
                    "cid": canonical_id,
                    "pid": orig_pid,
                    "store_name": lst.store_id,
                    "raw_title": lst.raw_title,
                    "norm_title": norm_t,
                    "price": lst.price,
                    "url": lst.url
                })
                listing_count += 1

        self.session.commit()

        summary = {
            "total_canonical_products": canonical_count,
            "total_store_listings": listing_count,
            "review_queue_items": review_count,
            "matched_groups": canonical_count - review_count
        }
        print("=" * 80)
        print("CANONICAL MATCHING COMPLETED SUCCESSFULLY!")
        print(f"Summary: {summary}")
        print("=" * 80)

        return summary

    def get_canonical_products(self, category: str | None = None, needs_review: bool | None = None, limit: int = 50) -> list[dict]:
        """Fetch canonical products and their associated store listings for API/GUI inspection."""
        where_clauses = []
        params = {"limit": limit}

        if category:
            where_clauses.append("cp.category = :category")
            params["category"] = category.lower()
        if needs_review is not None:
            where_clauses.append("cp.needs_review = :needs_review")
            params["needs_review"] = needs_review

        where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        query = text(f"""
            SELECT cp.id, cp.canonical_key, cp.category, cp.name, cp.attributes, cp.needs_review, cp.created_at,
                   COALESCE(json_agg(
                       json_build_object(
                           'id', sl.id,
                           'product_id', sl.product_id,
                           'store_name', sl.store_name,
                           'raw_title', sl.raw_title,
                           'normalized_title', sl.normalized_title,
                           'price', sl.price,
                           'product_url', sl.product_url
                       )
                   ) FILTER (WHERE sl.id IS NOT NULL), '[]'::json) AS listings
            FROM canonical_products_test cp
            LEFT JOIN store_listings_test sl ON cp.id = sl.canonical_product_id
            {where_str}
            GROUP BY cp.id
            ORDER BY cp.needs_review ASC, count(sl.id) DESC, cp.id DESC
            LIMIT :limit;
        """)

        rows = self.session.execute(query, params).fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r[0],
                "canonical_key": r[1],
                "category": r[2],
                "name": r[3],
                "attributes": r[4] if isinstance(r[4], dict) else (json.loads(r[4]) if r[4] else {}),
                "needs_review": r[5],
                "created_at": str(r[6]),
                "listings": r[7] if isinstance(r[7], list) else (json.loads(r[7]) if r[7] else [])
            })
        return result
