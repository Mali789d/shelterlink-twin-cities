"""Malformed geocoder results cannot escape the ZIP/place comparison guard."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.sms import parse_sms

BAD_COORDINATES = [
    (float("nan"), -93.2), (44.9, float("inf")), (91, -93.2),
    (44.9, -181), (True, -93.2), ("44.9", -93.2), (), (44.9,),
    (44.9, -93.2, 0), "coordinates", 42, {},
]


@pytest.mark.parametrize("bad", BAD_COORDINATES)
@pytest.mark.parametrize("bad_location", ["55415", "saint paul"])
def test_malformed_comparison_keeps_zip_for_normal_validation(bad, bad_location):
    def geocode(location):
        return bad if location == bad_location else (44.9778, -93.2650)
    query = parse_sms("shelter 55415 saint paul", geocode=geocode)
    assert query is not None
    assert query.location == "55415"


@pytest.mark.parametrize("bad", BAD_COORDINATES)
def test_webhook_still_answers_when_only_place_result_is_malformed(monkeypatch, bad):
    def geocode(location):
        return (44.9778, -93.2650) if location == "55415" else bad
    monkeypatch.setattr(main.geocoder, "geocode", geocode)
    monkeypatch.setattr(main, "reply_throttle", main.ReplyThrottle())
    response = TestClient(main.app).post("/sms", data={
        "Body": "shelter 55415 saint paul", "From": "+15555550701",
    })
    assert response.status_code == 200
    assert "Nearest resources" in response.text
    assert "211" in response.text and "911" in response.text


@pytest.mark.parametrize("bad", BAD_COORDINATES)
def test_bad_zip_cannot_reach_search_after_comparison_fallback(monkeypatch, bad):
    monkeypatch.setattr(main.geocoder, "geocode", lambda _location: bad)
    monkeypatch.setattr(main, "reply_throttle", main.ReplyThrottle())
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid coordinates must never reach search")
    monkeypatch.setattr(main, "find_resources", forbidden)
    response = TestClient(main.app).post("/sms", data={
        "Body": "shelter 55415 saint paul", "From": "+15555550702",
    })
    assert response.status_code == 200
    assert "Try a 5-digit Twin Cities ZIP" in response.text
    assert "Nearest resources" not in response.text
    assert "211" in response.text and "911" in response.text
