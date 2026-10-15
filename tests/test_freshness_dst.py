"""The 24-hour safety window is elapsed time, not local clock arithmetic."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.data import load_resources
from app.freshness import Freshness, resource_freshness, safe_availability
from app.models import Availability

CHICAGO = ZoneInfo("America/Chicago")


def item(verified):
    return load_resources()[0].model_copy(update={"is_sample": False,
                                                "verified_at": verified,
                                                "availability": Availability.AVAILABLE})


def test_fall_back_same_wall_time_is_25_hours_old():
    verified = datetime(2026, 10, 31, 12, tzinfo=CHICAGO)
    at = datetime(2026, 11, 1, 12, tzinfo=CHICAGO)
    assert resource_freshness(item(verified), at) is Freshness.STALE
    assert safe_availability(item(verified), at) is Availability.UNKNOWN


def test_spring_forward_24_hour_wall_difference_is_only_23_elapsed_hours():
    verified = datetime(2026, 3, 7, 12, tzinfo=CHICAGO)
    at = datetime(2026, 3, 8, 12, 30, tzinfo=CHICAGO)
    assert resource_freshness(item(verified), at) is Freshness.CURRENT


def test_repeated_hour_future_instant_does_not_pass_as_current():
    verified = datetime(2026, 11, 1, 1, 15, tzinfo=CHICAGO, fold=1)
    at = datetime(2026, 11, 1, 1, 45, tzinfo=CHICAGO, fold=0)
    assert resource_freshness(item(verified), at) is Freshness.STALE
    assert safe_availability(item(verified), at) is Availability.UNKNOWN


def test_exact_elapsed_boundary_and_one_microsecond_over():
    verified = datetime(2026, 10, 31, 12, tzinfo=CHICAGO)
    boundary = (verified.astimezone(timezone.utc) + timedelta(hours=24)).astimezone(CHICAGO)
    assert resource_freshness(item(verified), boundary) is Freshness.CURRENT
    assert resource_freshness(item(verified), boundary + timedelta(microseconds=1)) is Freshness.STALE


def test_same_instant_with_different_offset_has_same_result():
    verified = datetime(2026, 11, 1, 1, 15, tzinfo=CHICAGO, fold=1)
    at = datetime(2026, 11, 1, 2, tzinfo=CHICAGO)
    assert resource_freshness(item(verified), at) == resource_freshness(
        item(verified.astimezone(timezone.utc)), at.astimezone(timezone.utc))
