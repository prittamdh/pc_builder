"""
Experimental Script to Test LLM Feature Extraction using Groq (llama-3.1-8b-instant).
Extracts brand, model_series, and extracted_spec from product titles.
"""
import os
import sys
import json
import argparse
from sqlalchemy import text
from db.session import SessionLocal

try:
    from groq import Groq
except ImportError:
    print("[Error] 'groq' package is missing. Run: pip install groq")
    sys.exit(1)


# Schema focused strictly on structural spec isolation
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {
            "type": "string", 
            "description": "The manufacturer name, e.g., AMD, Kioxia, Adata, MSI, Western Digital, Arctic, Corsair, Gigabyte"
        },
        "model_series": {
            "type": "string", 
            "description": "The exact model name or product line, e.g., Ryzen 7 9800X3D, Exceria Plus G4, XPG Pylon, MAG B860M Mortar, Vengeance RGB"
        },
        "extracted_spec": {
            "type": "string", 
            "description": "The core technical specifications isolated from the title, e.g., 1TB, 750W, 32GB 5200MHz, 240mm, 21.5 inch 100Hz"
        }
    },
    "required": ["brand", "model_series", "extracted_spec"]
}


from configs.settings import GROQ_API_KEY

def test_groq_extraction(api_key: str | None = None, sample_size: int = 5):
    key = api_key or os.environ.get("GROQ_API_KEY") or GROQ_API_KEY
    if not key:
        print("\n[Error] GROQ_API_KEY is not set!")
        print("Please provide your API key in .env or run:")
        print("  python scripts/test_groq_extraction.py --api-key gsk_xxxx...")
        return

    client = Groq(api_key=key)

    with SessionLocal() as session:
        # Load sample live products across different component categories
        sql = text("""
            SELECT id, sid, pid, name, p_category 
            FROM products 
            WHERE in_stock = TRUE AND name IS NOT NULL 
            LIMIT :limit;
        """)
        rows = session.execute(sql, {"limit": sample_size}).fetchall()

    print("=" * 80)
    print(f"TESTING LLM FEATURE EXTRACTION (llama-3.1-8b-instant) ON {len(rows)} LIVE PRODUCTS")
    print("=" * 80)

    for r in rows:
        pid_id, sid, pid, name, p_cat = r
        print(f"\n[Product ID {pid_id}] Category: {p_cat}")
        print(f"  Title: '{name}'")

        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a hardware data extraction assistant. Extract structural specs from product title into JSON.\n"
                            "Keys required:\n"
                            "- \"brand\": Manufacturer name (e.g. Intel, AMD, Corsair, Kioxia, Kingston, Adata)\n"
                            "- \"model_series\": Full model name/line (e.g. Core i7-14700, Ryzen 7 9800X3D, Fury Beast)\n"
                            "- \"extracted_spec\": Technical specs (e.g. 16 Cores, 32GB 5200MHz, 1TB NVMe Gen5, 750W, 240mm)\n"
                            "Return ONLY a JSON object."
                        )
                    },
                    {"role": "user", "content": f"Product Title: {name}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )

            extracted = json.loads(response.choices[0].message.content)
            print("  Extracted Specs:")
            print(f"    - Brand:          {extracted.get('brand')}")
            print(f"    - Model Series:   {extracted.get('model_series')}")
            print(f"    - Extracted Spec: {extracted.get('extracted_spec')}")

        except Exception as e:
            print(f"  [Error] Extraction failed: {e}")

    print("\n" + "=" * 80)
    print("TEST FINISHED!")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Groq LLM Feature Extraction")
    parser.add_argument("--api-key", type=str, help="Groq API Key (gsk_xxxx...)")
    parser.add_argument("--sample-size", type=int, default=5, help="Number of sample products to test")
    args = parser.parse_args()

    test_groq_extraction(api_key=args.api_key, sample_size=args.sample_size)
