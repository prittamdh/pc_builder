"""
Script to test ModxComputers pagination with in_stock=true.
"""
import re
import json
from scrapers.http_client import HttpClient

def test_modx_pages():
    client = HttpClient()
    url = "https://modxcomputers.com/product-category/pc-components/cabinets/?in_stock=true"
    r = client.get(url)
    
    match = re.search(r'"productData"\s*:\s*(\{.*?"data"\s*:\s*\[.*?\]\})', r.text)
    if not match:
        match = re.search(r'productData\\":(\{.*?\\"data\\":\[.*?\]\})', r.text)
        
    if match:
        raw_json = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
        try:
            pdata = json.loads(raw_json)
            total = pdata.get("total")
            count = len(pdata.get("data", []))
            print(f"Modx Cabinets (in_stock=true): total={total}, page 1 count={count}")
        except Exception as e:
            print("Error parsing JSON:", e)
    else:
        print("No productData found.")

    # Test page=2, page=3, page=4
    for p in range(1, 10):
        p_url = f"https://modxcomputers.com/product-category/pc-components/cabinets/?in_stock=true&page={p}"
        r2 = client.get(p_url)
        match2 = re.search(r'"productData"\s*:\s*(\{.*?"data"\s*:\s*\[.*?\]\})', r2.text)
        if not match2:
            match2 = re.search(r'productData\\":(\{.*?\\"data\\":\[.*?\]\})', r2.text)
        if match2:
            try:
                pdata2 = json.loads(match2.group(1).replace('\\"', '"').replace('\\\\', '\\'))
                prods = pdata2.get("data", [])
                if prods:
                    instock = [x for x in prods if (x.get("stockStatus") or "").lower() == "instock"]
                    print(f"  Page {p}: {len(prods)} products | {len(instock)} instock (First item: {prods[0].get('name')[:30]})")
                else:
                    print(f"  Page {p}: 0 products (exhausted).")
                    break
            except Exception:
                pass

if __name__ == "__main__":
    test_modx_pages()
