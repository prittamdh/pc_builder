"""
Test script for Phase 9 Frontend routes.
"""
from fastapi.testclient import TestClient
from api.main import app


def test_frontend_routes():
    client = TestClient(app)

    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "PC Builder 2" in res_index.text
    print("[GET /] -> 200 OK (Served index.html)")

    res_css = client.get("/static/style.css")
    assert res_css.status_code == 200
    assert "--bg-dark" in res_css.text
    print("[GET /static/style.css] -> 200 OK")

    res_js = client.get("/static/app.js")
    assert res_js.status_code == 200
    assert "API_BASE" in res_js.text
    print("[GET /static/app.js] -> 200 OK")

    print("\n[OK] Phase 9 Frontend UI static files & routing verified successfully!")


if __name__ == "__main__":
    test_frontend_routes()
