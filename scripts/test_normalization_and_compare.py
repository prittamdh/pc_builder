"""
Test script for Category Classification, Spec Normalization, and Price Comparison API.
"""
from fastapi.testclient import TestClient
from api.main import app
from db.session import SessionLocal
from matching.category_classifier import CategoryClassifier
from matching.spec_normalizer import SpecNormalizer
from services.normalization_service import NormalizationService


def test_normalizer():
    print("=" * 80)
    print("Testing Category Classifier & Spec Normalizer")
    print("=" * 80)

    cat = CategoryClassifier.classify("AMD Ryzen 7 7800X3D 8-Core Desktop Processor")
    print(f"Classified CPU: {cat}")
    assert cat == "CPU"

    norm_cpu = SpecNormalizer.normalize_cpu("AMD Ryzen 7 7800X3D 8-Core Desktop Processor AM5 120W", {})
    print(f"Normalized CPU Specs: {norm_cpu}")
    assert norm_cpu.get("socket") == "AM5"
    assert norm_cpu.get("cores") == 8

    cat_gpu = CategoryClassifier.classify("MSI Gaming GeForce RTX 5080 16G GDDR7")
    print(f"Classified GPU: {cat_gpu}")
    assert cat_gpu == "GPU"

    norm_gpu = SpecNormalizer.normalize_gpu("MSI Gaming GeForce RTX 5080 16G GDDR7", {})
    print(f"Normalized GPU Specs: {norm_gpu}")
    assert norm_gpu.get("chipset") == "RTX 5080"
    assert norm_gpu.get("memory_size_gb") == 16


def test_normalization_service():
    print("=" * 80)
    print("Testing Normalization Pipeline Service")
    print("=" * 80)
    with SessionLocal() as session:
        service = NormalizationService(session)
        count = service.normalize_all_unclassified(limit=50)
        print(f"Normalized {count} catalog products.")


def test_compare_api():
    print("=" * 80)
    print("Testing Price Comparison Endpoint GET /api/v1/compare")
    print("=" * 80)
    client = TestClient(app)

    res = client.get("/api/v1/compare?q=rtx")
    assert res.status_code == 200
    data = res.json()
    print(f"[GET /api/v1/compare?q=rtx]: Query='{data['query']}', Offers={data['total_offers']}")
    print(f"  Lowest Price = {data.get('lowest_price')}")
    print(f"  Highest Price = {data.get('highest_price')}")
    print(f"  Average Price = {data.get('average_price')}")

    print("\n[OK] Classification, Normalization, & Compare API tests passed successfully!")


if __name__ == "__main__":
    test_normalizer()
    test_normalization_service()
    test_compare_api()
