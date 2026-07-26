import sys
from pathlib import Path

# Add src to sys.path
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_builder_tool():
    print("=" * 80)
    print("Testing PC Builder Assembly Tool Endpoints")
    print("=" * 80)

    # 1. Get Slots
    res = client.get("/api/v1/builder/slots")
    assert res.status_code == 200, f"Get slots failed: {res.text}"
    slots = res.json()
    print(f"[GET /api/v1/builder/slots]: Loaded {len(slots)} component slots.")

    # 2. Get sample product IDs for build
    res = client.get("/api/v1/products?size=5")
    products = res.json()["items"]
    sample_ids = [p["id"] for p in products[:3]]

    # 3. Validate Build
    res = client.post("/api/v1/builder/validate", json={"selected_product_ids": sample_ids})
    assert res.status_code == 200, f"Validate build failed: {res.text}"
    summary = res.json()

    print(f"[POST /api/v1/builder/validate]:")
    print(f"  Compatible: {summary['compatible']}")
    print(f"  Estimated Wattage: {summary['estimated_wattage']}W")
    print(f"  Total Min Cost: INR {summary['total_min_cost']}")
    print(f"  Warnings: {len(summary['warnings'])}")

    print("\n[OK] PC Builder Assembly Tool endpoints verified successfully!")


if __name__ == "__main__":
    test_builder_tool()
