"""An optional radius prevents distant results from being mistaken for nearby help."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.data import load_resources
from app.search import distance_miles, find_resources

AT = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def records():
    base = load_resources()[0]
    return [base.model_copy(update={"id": identity, "latitude": 0.0, "longitude": longitude,
                                    "verified_at": AT, "is_sample": False})
            for identity, longitude in [("far", 1.0), ("near", 0.001), ("origin", 0.0)]]


def test_radius_filters_before_limit_and_preserves_ranking():
    result = find_resources(records(), 0, 0, limit=2, at=AT, radius_miles=1)
    assert [item.resource.id for item in result] == ["origin", "near"]


def test_omitted_radius_preserves_existing_results():
    assert len(find_resources(records(), 0, 0, at=AT)) == 3


def test_zero_radius_only_matches_same_point():
    assert [item.resource.id for item in find_resources(records(), 0, 0, at=AT,
                                                       radius_miles=0)] == ["origin"]


def test_boundary_is_inclusive_and_uses_unrounded_distance():
    near = records()[1]
    boundary = distance_miles(0, 0, near.latitude, near.longitude)
    assert len(find_resources([near], 0, 0, at=AT, radius_miles=boundary)) == 1
    assert find_resources([near], 0, 0, at=AT, radius_miles=boundary - 0.000001) == []


@pytest.mark.parametrize("radius", [-1, float("nan"), float("inf"), float("-inf")])
def test_invalid_radius_rejected_even_with_empty_directory(radius):
    with pytest.raises(ValueError, match="radius"):
        find_resources([], 0, 0, radius_miles=radius)


@pytest.mark.parametrize("radius", ["-1", "nan", "inf", "-inf", "not-a-number"])
def test_api_rejects_invalid_radius(radius):
    response = TestClient(main.app).get("/resources/search",
        params={"lat": 0, "lon": 0, "radius_miles": radius})
    assert response.status_code == 422


def test_api_radius_and_empty_results(monkeypatch):
    monkeypatch.setattr(main, "resources", records())
    client = TestClient(main.app)
    response = client.get("/resources/search", params={"lat": 0, "lon": 0, "radius_miles": 0})
    assert response.status_code == 200
    assert [item["resource"]["id"] for item in response.json()] == ["origin"]
    assert client.get("/resources/search", params={"lat": 10, "lon": 10,
                                                  "radius_miles": 1}).json() == []
