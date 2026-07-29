"""
Inspect ModxComputers category pages and stock attributes.
"""
import re
import json
from scrapers.http_client import HttpClient

def test_modx_all():
    client = HttpClient()
    categories = [
        "product-category/pc-components/processor/",
        "product-category/pc-components/motherboard/",
        "product-category/pc-components/graphics-card/",
        "product-category/pc-components/cabinets/",
        "product-category/pc-components/power-supply/",
    ]
    for cat in categories:
        url = f"https://modxcomputers.com/{cat}"
        r = client.get(url)
        match = re.search(r'"productData"\s*:\s*(\{.*?"data"\s*:\s*\[.*?\]\})', r.text)
        if not match:
            match = re.search(r'productData\\":(\{.*?\\"data\\":\[.*?\]\})', r.text)
            
        if match:
            raw_json = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
            try:
                data = json.loads(raw_json).get("data", [])
                print(f"[{cat}] Found {len(data)} total products:")
                for i, p in enumerate(data, 1):
                    name = (p.get("name") or "")[:35].encode('ascii', 'ignore').decode('ascii')
                    st = p.get("stockStatus")
                    stock = p.get("stock")
                    print(f"  {i}. {name} | stockStatus: {st} | stock: {stock}")
            except Exception as e:
                print(f"[{cat}] JSON Parse error: {e}")
        else:
            print(f"[{cat}] No productData match.")

if __name__ == "__main__":
    test_modx_all()
