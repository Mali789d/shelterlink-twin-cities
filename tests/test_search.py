from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.data import load_resources
from app.models import ResourceCategory
from app.search import distance_miles, find_resources


def test_distance_is_zero_for_same_point():
    assert distance_miles(44.97, -93.26, 44.97, -93.26) == 0


def test_results_are_sorted_by_distance():
    results = find_resources(load_resources(), 44.9778, -93.2650)
    assert results[0].resource.id == "sample-minneapolis-shelter"
    assert results[0].distance_miles <= results[1].distance_miles


def test_category_filter():
    results = find_resources(
        load_resources(), 44.9778, -93.2650, category=ResourceCategory.MEAL
    )
    assert len(results) == 1
    assert results[0].resource.category == ResourceCategory.MEAL


def test_open_now_filter_excludes_unverified_sample_hours():
    monday_noon = datetime(2026, 9, 21, 12, tzinfo=ZoneInfo("America/Chicago"))
    results = find_resources(load_resources(), 44.95, -93.09, open_now=True, at=monday_noon)
    assert results == []
    all_results = find_resources(load_resources(), 44.95, -93.09, at=monday_noon)
    assert all(not item.open_now for item in all_results)


def test_fresh_nonsample_hours_can_be_marked_open_and_filtered():
    monday_noon = datetime(2026, 9, 21, 12, tzinfo=ZoneInfo("America/Chicago"))
    fresh = load_resources()[0].model_copy(update={
        "is_sample": False, "verified_at": monday_noon - timedelta(hours=2)
    })
    results = find_resources([fresh], 44.97, -93.26, open_now=True, at=monday_noon)
    assert len(results) == 1 and results[0].open_now


def test_stale_and_future_hours_are_not_marked_open():
    monday_noon = datetime(2026, 9, 21, 12, tzinfo=ZoneInfo("America/Chicago"))
    base = load_resources()[0]
    for verified_at in (monday_noon - timedelta(hours=25), monday_noon + timedelta(minutes=1)):
        item = base.model_copy(update={"is_sample": False, "verified_at": verified_at})
        results = find_resources([item], 44.97, -93.26, at=monday_noon)
        assert len(results) == 1 and not results[0].open_now
        assert find_resources([item], 44.97, -93.26, open_now=True, at=monday_noon) == []


def test_stale_source_never_exposes_reported_availability():
    observed = datetime(2026, 9, 23, 12, tzinfo=ZoneInfo("America/Chicago"))
    result = find_resources(load_resources(), 44.9778, -93.2650, at=observed)[0]
    assert result.data_freshness == "stale"
    assert result.availability.value == "unknown"
