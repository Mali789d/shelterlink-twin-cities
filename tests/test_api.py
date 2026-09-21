from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_search_endpoint():
    response = client.get(
        "/resources/search",
        params={"lat": 44.9778, "lon": -93.2650, "category": "shelter"},
    )
    assert response.status_code == 200
    assert response.json()[0]["resource"]["category"] == "shelter"


def test_sms_endpoint_returns_twiml():
    response = client.post("/sms", data={"Body": "55415 shelter"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "Nearest resources" in response.text


def test_sms_endpoint_guides_invalid_location():
    response = client.post("/sms", data={"Body": "somewhere far away"})
    assert "couldn&#x27;t find" in response.text
