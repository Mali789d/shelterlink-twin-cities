"""The search API resolves a known place or explicit coordinates, never a guess."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def test_location_zip_resolves_to_search_results():
    response = client.get("/resources/search", params={"location": "55415"})
    assert response.status_code == 200
    assert response.json(), "a downtown ZIP should find sample resources"


def test_location_city_name_trims_case_and_whitespace():
    response = client.get("/resources/search", params={"location": "  Minneapolis "})
    assert response.status_code == 200


def test_unknown_location_is_a_client_error_not_a_guess():
    response = client.get("/resources/search", params={"location": "nowhere particular"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown location"


def test_blank_location_rejected():
    response = client.get("/resources/search", params={"location": "   "})
    assert response.status_code == 400


def test_location_and_coordinates_conflict_rejected():
    response = client.get("/resources/search",
                          params={"location": "55415", "lat": 44.97, "lon": -93.26})
    assert response.status_code == 400
    assert "not both" in response.json()["detail"]


def test_lat_without_lon_rejected():
    response = client.get("/resources/search", params={"lat": 44.97})
    assert response.status_code == 400
    assert "together" in response.json()["detail"]


def test_no_coordinate_source_rejected():
    response = client.get("/resources/search")
    assert response.status_code == 400


def test_explicit_coordinates_still_work():
    response = client.get("/resources/search", params={"lat": 44.9778, "lon": -93.2650})
    assert response.status_code == 200


def test_broken_geocoder_is_a_server_error_not_a_search(monkeypatch):
    monkeypatch.setattr(main.geocoder, "geocode", lambda location: (999.0, 999.0))
    response = client.get("/resources/search", params={"location": "55415"})
    assert response.status_code == 503


def test_raising_geocoder_is_a_server_error_not_a_500(monkeypatch):
    def explode(location):
        raise RuntimeError("provider down")

    monkeypatch.setattr(main.geocoder, "geocode", explode)
    response = client.get("/resources/search", params={"location": "55415"})
    assert response.status_code == 503


def test_location_accepts_an_explicit_coordinate_string():
    response = client.get("/resources/search",
                          params={"location": "44.9778,-93.2650"})
    assert response.status_code == 200
    assert response.json(), "downtown coordinates should find sample resources"


def test_location_coordinate_string_matches_the_split_pair():
    as_string = client.get("/resources/search",
                           params={"location": "44.9778,-93.2650"})
    as_pair = client.get("/resources/search",
                         params={"lat": 44.9778, "lon": -93.2650})
    assert as_string.status_code == as_pair.status_code == 200
    assert as_string.json() == as_pair.json()


def test_out_of_range_coordinate_string_is_not_a_search_point():
    response = client.get("/resources/search", params={"location": "44.9,-999"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown location"


def test_coordinate_string_still_conflicts_with_a_split_pair():
    response = client.get("/resources/search",
                          params={"location": "44.9778,-93.2650", "lat": 44.97})
    assert response.status_code == 400
    assert "not both" in response.json()["detail"]
