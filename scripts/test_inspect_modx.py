"""
Script to inspect ModxComputers payload structure.
"""
from bs4 import BeautifulSoup
import json
import re
from scrapers.http_client import HttpClient

def inspect_modx():
    client = HttpClient()
    r = client.get("https://modxcomputers.com/product-category/pc-components/processor/")
    soup = BeautifulSoup(r.text, "lxml")
    
    scripts = soup.find_all("script")
    print(f"Total script tags in Modx HTML: {len(scripts)}")
    
    for idx, s in enumerate(scripts, 1):
        content = s.string or ""
        if "processor" in content.lower() or "ryzen" in content.lower() or "price" in content.lower():
            print(f"\n--- Script #{idx} (length {len(content)}) ---")
            print(content[:300].encode("ascii", "ignore").decode("ascii"))
            
            # Find embedded JSON objects
            json_matches = re.findall(r'(\{"id":\d+,"name":[^}]+\})', content)
            if json_matches:
                print(f"Found {len(json_matches)} product JSON objects in script #{idx}!")
                for i, jm in enumerate(json_matches[:3], 1):
                    print(f"  Match {i}: {jm[:150].encode('ascii', 'ignore').decode('ascii')}")

if __name__ == "__main__":
    inspect_modx()
