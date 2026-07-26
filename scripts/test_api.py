import sys
from pathlib import Path

# Add src to sys.path
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_api():
    print("=" * 80)
    print("Testing FastAPI Endpoints")
    print("=" * 80)

    # 1. Health Check & Frontend Root
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print(f"[GET /health]: {res.json()}")

    res = client.get("/")
    assert res.status_code == 200, "Frontend index.html failed to serve"
    assert "PC BUILDER 2" in res.text, "Index HTML missing title brand"
    print("[GET /]: Frontend HTML index served successfully.")

    res = client.get("/static/index.css")
    assert res.status_code == 200, "Static CSS failed to serve"
    print("[GET /static/index.css]: Static CSS served successfully.")

    # 2. List Stores
    res = client.get("/api/v1/stores")
    assert res.status_code == 200, f"List stores failed: {res.text}"
    stores = res.json()
    print(f"[GET /api/v1/stores]: Found {len(stores)} active stores.")
    assert len(stores) > 0, "No active stores returned."

    # 3. List Products
    res = client.get("/api/v1/products?q=rtx&size=5")
    assert res.status_code == 200, f"List products failed: {res.text}"
    data = res.json()
    print(f"[GET /api/v1/products?q=rtx]: Total matching = {data['total']}, Returned = {len(data['items'])}")

    if data["items"]:
        first_id = data["items"][0]["id"]
        # 4. Get Product Details
        res = client.get(f"/api/v1/products/{first_id}")
        assert res.status_code == 200, f"Get product failed: {res.text}"
        prod = res.json()
        print(f"[GET /api/v1/products/{first_id}]: {prod['name']} | Price: INR {prod['current_price']}")

        # 5. Get Product Price History
        res = client.get(f"/api/v1/products/{first_id}/history")
        assert res.status_code == 200, f"Get price history failed: {res.text}"
        history = res.json()
        print(f"[GET /api/v1/products/{first_id}/history]: {len(history)} price snapshots found.")

    print("\n[OK] All FastAPI endpoints verified successfully!")


if __name__ == "__main__":
    test_api()
