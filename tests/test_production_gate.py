from fastapi.testclient import TestClient

import app.main as main
from app.models import Resource
from app.security import compute_signature

client = TestClient(main.app)
BASE = "https://sms.shelterlink.example"


def signed_sms(body):
    form = {"Body": body, "From": "+16125550100"}
    signature = compute_signature("test-token", BASE + "/sms", form)
    return client.post("/sms", data=form, headers={"X-Twilio-Signature": signature})


def test_production_sample_data_does_not_escape_via_search_or_sms(monkeypatch):
    monkeypatch.setenv("SHELTERLINK_ENV", "production")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    response = client.get("/resources/search", params={"lat": 44.9778, "lon": -93.2650})
    assert response.status_code == 503
    assert "Verified resource data is not available" in response.text
    for body, expected in (("55415 shelter", "not live yet"),
                           ("55415 shelter lang es", "todavía no"),
                           ("55415 shelter lang so", "weli")):
        response = signed_sms(body)
        assert response.status_code == 200
        assert expected.replace(" ", "") in response.text.replace(" ", "")
        assert "Sample" not in response.text
        assert "211" in response.text and "911" in response.text


def test_keywords_still_work_with_sample_gate(monkeypatch):
    monkeypatch.setenv("SHELTERLINK_ENV", "production")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    monkeypatch.setattr(main, "opt_outs", main.InMemoryOptOutStore(salt="test"))
    assert signed_sms("STOP").status_code == 200
    assert "<Message>" not in signed_sms("55415 shelter").text
    assert "ShelterLink" in signed_sms("HELP").text
    assert "subscribed again" in signed_sms("START").text
    assert "not live yet" in signed_sms("55415 shelter").text


def test_verified_data_can_pass_gate(monkeypatch):
    monkeypatch.setenv("SHELTERLINK_ENV", "production")
    real: Resource = main.resources[0].model_copy(update={"is_sample": False})
    monkeypatch.setattr(main, "resources", [real])
    response = client.get("/resources/search", params={"lat": 44.9778, "lon": -93.2650})
    assert response.status_code == 200
    assert response.json()[0]["resource"]["id"] == real.id


def test_empty_production_data_does_not_look_like_no_matching_resources(monkeypatch):
    monkeypatch.setenv("SHELTERLINK_ENV", "production")
    monkeypatch.setattr(main, "resources", [])
    assert client.get("/resources/search", params={"lat": 44.97, "lon": -93.26}).status_code == 503
