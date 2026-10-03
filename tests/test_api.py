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
    response = client.post("/sms", data={"From": "+16125550100", "Body": "55415 shelter"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "Nearest resources" in response.text


def test_sms_endpoint_guides_invalid_location():
    response = client.post("/sms", data={"From": "+16125550100", "Body": "somewhere far away"})
    assert "couldn&#x27;t find" in response.text


def test_sms_endpoint_supports_spanish():
    response = client.post("/sms", data={"From": "+16125550100", "Body": "55415 shelter lang es"})
    assert "Recursos más cercanos" in response.text
    assert "La información puede cambiar" in response.text


def test_sms_endpoint_supports_somali():
    response = client.post("/sms", data={"From": "+16125550100", "Body": "55415 shelter lang so"})
    assert "Adeegyada kuugu dhow" in response.text
    assert "Xogtu way is beddeli kartaa" in response.text


import pytest


@pytest.mark.parametrize("body,heading", [
    ("55101 comida lang es", "Recursos más cercanos"),
    ("Saint Paul cunto lang so", "Adeegyada kuugu dhow"),
])
def test_translated_service_words_filter_results(body, heading):
    response = client.post("/sms", data={"From": "+16125550199", "Body": body})
    assert response.status_code == 200
    assert heading in response.text
    assert "Sample Saint Paul Meal Site" in response.text
    assert "Sample Minneapolis Shelter" not in response.text
    assert "211" in response.text and "911" in response.text


def test_multiple_services_do_not_silently_send_one_category():
    response = client.post("/sms", data={"From": "+16125550199", "Body": "55415 food shower"})
    assert response.status_code == 200
    assert "Sample" not in response.text
    assert "Text a Twin Cities ZIP" in response.text
