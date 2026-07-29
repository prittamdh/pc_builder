"""
Test script for ModxComputers Next.js App Router productData parser.
"""
import json
import re
from scrapers.http_client import HttpClient

def test_modx_parser():
    client = HttpClient()
    r = client.get("https://modxcomputers.com/product-category/pc-components/processor/")
    
    # Extract productData payload from script tags
    match = re.search(r'"productData"\s*:\s*(\{.*?"data"\s*:\s*\[.*?\]\})', r.text)
    if not match:
        # Alternative regex if nested
        match = re.search(r'productData\\":(\{.*?\\"data\\":\[.*?\]\})', r.text)
        
    if match:
        raw_json = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
        try:
            pdata = json.loads(raw_json)
            prods = pdata.get("data", [])
            print(f"ModxComputers extracted {len(prods)} products from productData!")
            for idx, p in enumerate(prods[:5], 1):
                name = p.get("name")
                slug = p.get("slug")
                price = p.get("salePrice") or p.get("price") or p.get("discountPrice")
                mrp = p.get("mrp") or price
                in_stock = p.get("inStock") or p.get("stock_status") == "instock"
                print(f"  {idx}. {name} | Slug: {slug} | Price: {price} | MRP: {mrp} | InStock: {in_stock}")
        except Exception as e:
            print("Failed to parse JSON:", e)
    else:
        print("No productData match found in HTML.")

if __name__ == "__main__":
    test_modx_parser()
