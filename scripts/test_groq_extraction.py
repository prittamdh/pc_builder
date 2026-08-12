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
    print(f"TESTING HIERARCHICAL LLM FEATURE EXTRACTION (llama-3.1-8b-instant) ON {len(rows)} PRODUCTS")
    print("=" * 80)

    # Ultra-lean system prompt (Token Efficient: <120 tokens)
    system_prompt = (
        "Extract hardware specs into JSON. Return ONLY JSON.\n"
        "Schema:\n"
        "{\n"
        '  "brand": "Brand",\n'
        '  "model_series": "Model line/number",\n'
        '  "specs_in_title": {"explicit_spec": "text in title"},\n'
        '  "specs_inferred": {"total_cores": 16, "p_cores": 8, "e_cores": 8, "socket": "LGA1700"},\n'
        '  "hierarchical": {\n'
        '    "family": "i7/Ryzen 9/RTX 5070",\n'
        '    "variant": "14700KF/9900X",\n'
        '    "igpu": "Radeon Graphics/Intel UHD 770/None",\n'
        '    "capacity": "32GB/1TB",\n'
        '    "speed": "6000MHz/10000MBs",\n'
        '    "form_factor_size": "240mm/120mm/ATX"\n'
        "  }\n"
        "}"
    )

    for r in rows:
        pid_id, sid, pid, name, p_cat = r
        print(f"\n[Product ID {pid_id}] Category: {p_cat}")
        print(f"  Title: '{name}'")

        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Category: {p_cat} | Title: {name}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )

            usage = response.usage
            tokens_info = f"Prompt Tokens: {usage.prompt_tokens} | Completion Tokens: {usage.completion_tokens} | Total: {usage.total_tokens}" if usage else ""

            extracted = json.loads(response.choices[0].message.content)
            print("  Extracted Specs:")
            print(f"    - Brand:            {extracted.get('brand')}")
            print(f"    - Model Series:     {extracted.get('model_series')}")
            print(f"    - Specs In Title:   {extracted.get('specs_in_title')}")
            print(f"    - Specs Inferred:   {extracted.get('specs_inferred')}")
            print(f"    - Hierarchical:     {extracted.get('hierarchical')}")
            if tokens_info:
                print(f"    [Token Usage] {tokens_info}")

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
