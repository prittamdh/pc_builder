from pathlib import Path

from scrapers.sites.mdcomputers_parser import MDComputersParser

html = Path("mdcomputers.html").read_text(encoding="utf-8")

parser = MDComputersParser()

results = parser.parse_search(html)

print(f"Found {len(results)} products\n")

for result in results[:3]:
    print(result)
    print()