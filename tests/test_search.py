from datetime import datetime
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


def test_open_now_filter_uses_local_hours():
    monday_noon = datetime(2026, 9, 21, 12, tzinfo=ZoneInfo("America/Chicago"))
    results = find_resources(
        load_resources(), 44.95, -93.09, open_now=True, at=monday_noon
    )
    assert {item.resource.id for item in results} == {
        "sample-minneapolis-shelter",
        "sample-st-paul-meal",
    }


def test_stale_source_never_exposes_reported_availability():
    observed = datetime(2026, 9, 23, 12, tzinfo=ZoneInfo("America/Chicago"))
    result = find_resources(load_resources(), 44.9778, -93.2650, at=observed)[0]
    assert result.data_freshness == "stale"
    assert result.availability.value == "unknown"
