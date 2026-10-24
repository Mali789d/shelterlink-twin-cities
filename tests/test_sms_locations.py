"""Ambiguous ZIP requests cannot silently choose a referral location."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sms import parse_sms


@pytest.mark.parametrize("text", ["shelter 55415 or 55101", "meal 55101 55415",
                                  "refugio 55415 55101 lang:es",
                                  "cunto 55415 55101 lang:so"])
def test_distinct_zips_require_clarification(text):
    assert parse_sms(text) is None


def test_repeated_same_zip_is_unambiguous():
    assert parse_sms("shelter 55415 near 55415").location == "55415"


def test_zip_plus_four_keeps_existing_five_digit_routing():
    assert parse_sms("shelter 55415-1234").location == "55415"


def test_ambiguous_location_never_calls_geocoder(monkeypatch):
    from app import main
    def forbidden(location):
        raise AssertionError("ambiguous location must not be geocoded")
    monkeypatch.setattr(main.geocoder, "geocode", forbidden)
    response = TestClient(app).post("/sms", data={"Body": "shelter 55415 or 55101",
                                                "From": "+15555550100"})
    assert response.status_code == 200
    assert "Text a Twin Cities ZIP or location" in response.text
    assert "sample-minneapolis" not in response.text


@pytest.mark.parametrize("text", ["meal 55415", "shower saint paul", "warming minneapolis"])
def test_existing_single_location_requests_remain_supported(text):
    assert parse_sms(text) is not None


@pytest.mark.parametrize("text,expected", [
    ("shelter in minneapolis", "minneapolis"),
    ("food near saint paul", "saint paul"),
    ("shelter around minneapolis", "minneapolis"),
    ("shower at minneapolis", "minneapolis"),
    ("meal by minneapolis", "minneapolis"),
    ("in minneapolis", "minneapolis"),
])
def test_leading_preposition_drops_before_named_location(text, expected):
    query = parse_sms(text)
    assert query is not None
    assert query.location == expected


def test_place_name_starting_with_preposition_letters_is_untouched():
    query = parse_sms("shelter inver grove heights")
    assert query is not None
    assert query.location == "inver grove heights"


@pytest.mark.parametrize("text", ["shelter in", "in", "food near"])
def test_trailing_preposition_alone_asks_for_a_location(text):
    assert parse_sms(text) is None


def test_texted_coordinates_remain_the_location():
    query = parse_sms("shelter 44.9778,-93.2650")
    assert query is not None
    assert query.location == "44.9778,-93.2650"


def test_sms_webhook_accepts_texted_coordinates():
    response = TestClient(app).post("/sms", data={"Body": "shelter 44.9778,-93.2650",
                                                "From": "+15555550101"})
    assert response.status_code == 200
    assert "couldn&#x27;t find that location" not in response.text
    assert "Sample Minneapolis Shelter" in response.text


def test_sms_webhook_rejects_out_of_range_coordinates_without_guessing():
    response = TestClient(app).post("/sms", data={"Body": "shelter 44.9,-999",
                                                "From": "+15555550102"})
    assert response.status_code == 200
    assert "couldn&#x27;t find that location" in response.text
    assert "Sample Minneapolis Shelter" not in response.text


def test_texted_city_variants_reach_the_same_search():
    client = TestClient(app)
    for body in ("shelter st. paul", "shelter St. Paul, MN",
                 "shelter west st. paul, minnesota"):
        response = client.post("/sms", data={"Body": body, "From": "+15555550100"})
        assert response.status_code == 200, body
        assert "Text a Twin Cities ZIP or location" not in response.text, body
