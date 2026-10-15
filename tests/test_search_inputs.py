"""Direct geocoder/search callers need the same guardrails as the HTTP boundary."""
import pytest

from app.search import distance_miles, find_resources


@pytest.mark.parametrize("lat,lon", [(91, 0), (-91, 0), (0, 181), (0, -181),
                                     (float("nan"), 0), (0, float("inf")),
                                     (True, 0), (0, False), ("44.9", 0), (None, 0)])
def test_bad_coordinates_rejected_before_empty_search_or_distance_math(lat, lon):
    with pytest.raises(ValueError, match="coordinates"):
        find_resources([], lat, lon)
    with pytest.raises(ValueError, match="coordinates"):
        distance_miles(lat, lon, 0, 0)
    with pytest.raises(ValueError, match="coordinates"):
        distance_miles(0, 0, lat, lon)


@pytest.mark.parametrize("limit", [-1, 0, 11, 1.5, True, "3", None])
def test_bad_limit_cannot_silently_slice_results(limit):
    with pytest.raises(ValueError, match="limit"):
        find_resources([], 0, 0, limit=limit)


@pytest.mark.parametrize("radius", [True, "1", object()])
def test_invalid_radius_types_fail_with_clear_validation(radius):
    with pytest.raises(ValueError, match="radius"):
        find_resources([], 0, 0, radius_miles=radius)


@pytest.mark.parametrize("lat,lon", [(-90, -180), (90, 180), (0, 0)])
def test_coordinate_endpoints_remain_valid(lat, lon):
    assert find_resources([], lat, lon) == []
    assert distance_miles(lat, lon, lat, lon) == 0
