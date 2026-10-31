"""Display rounding must not choose the wrong nearest resource."""
from datetime import datetime, timezone

import pytest

from app.data import load_resources
from app.search import distance_miles, find_resources

AT = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def nearby(identity, longitude):
    return load_resources()[0].model_copy(update={
        "id": identity, "latitude": 0.0, "longitude": longitude,
        "verified_at": AT, "is_sample": False,
    })


def test_closest_wins_even_when_both_display_as_same_distance():
    farther, closer = nearby("farther", 0.0006), nearby("closer", 0.0001)
    results = find_resources([farther, closer], 0, 0, limit=1, at=AT)
    assert results[0].resource.id == "closer"
    assert results[0].distance_miles == 0.0


def test_full_ranking_uses_unrounded_distance_not_input_order():
    records = [nearby("far", 0.0026), nearby("middle", 0.0021), nearby("near", 0.0016)]
    results = find_resources(records, 0, 0, limit=3, at=AT)
    assert [item.resource.id for item in results] == ["near", "middle", "far"]
    assert [item.distance_miles for item in results] == [0.1, 0.1, 0.2]


def test_true_equal_distance_breaks_ties_by_id_not_input_order():
    # The same tie policy as web/directory.mjs nearbyResources: co-located
    # services rank by id, so a data-file reorder never changes who is listed
    # first - or who makes the cut at the limit.
    first = find_resources([nearby("b-site", 0.001), nearby("a-site", -0.001)],
                           0, 0, at=AT)
    second = find_resources([nearby("a-site", -0.001), nearby("b-site", 0.001)],
                            0, 0, at=AT)
    assert [item.resource.id for item in first] == ["a-site", "b-site"]
    assert [item.resource.id for item in second] == ["a-site", "b-site"]


@pytest.mark.parametrize("latitude,longitude", [(44.9778, -93.265), (-33.9, 151.2),
                                              (89.9, 12.3), (0, 0)])
def test_antipodal_roundoff_cannot_cause_domain_error(latitude, longitude):
    opposite_longitude = longitude + 180 if longitude <= 0 else longitude - 180
    distance = distance_miles(latitude, longitude, -latitude, opposite_longitude)
    assert distance == pytest.approx(12436.8154, abs=0.01)


def test_filtering_still_precedes_nearest_limit():
    records = [nearby("filtered", 0.0001).model_copy(update={"hours": {}}),
               nearby("open", 0.0006).model_copy(update={"hours": {0: [("00:00", "24:00")]}})]
    assert [item.resource.id for item in find_resources(records, 0, 0, open_now=True,
                                                      limit=1, at=AT)] == ["open"]
