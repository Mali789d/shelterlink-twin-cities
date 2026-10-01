from datetime import datetime, timedelta, timezone

import pytest

from app.freshness import Freshness, resource_freshness, safe_availability
from app.models import Availability, Resource, ResourceCategory
from pydantic import ValidationError


def resource(verified_at: datetime, availability: Availability = Availability.AVAILABLE):
    return Resource(
        id="test",
        name="Test resource",
        category=ResourceCategory.SHELTER,
        address="Minneapolis, MN",
        latitude=44.97,
        longitude=-93.26,
        availability=availability,
        source_name="Test source",
        source_url="https://example.com/source",
        verified_at=verified_at,
        is_sample=False,
    )


def test_current_data_keeps_reported_availability():
    now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    item = resource(now - timedelta(hours=2))
    assert resource_freshness(item, now) == Freshness.CURRENT
    assert safe_availability(item, now) == Availability.AVAILABLE


def test_stale_data_downgrades_availability_to_unknown():
    now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    item = resource(now - timedelta(hours=25))
    assert resource_freshness(item, now) == Freshness.STALE
    assert safe_availability(item, now) == Availability.UNKNOWN


def test_future_verification_timestamp_is_stale():
    now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    assert resource_freshness(resource(now + timedelta(minutes=1)), now) == Freshness.STALE


def test_naive_timestamp_is_rejected():
    now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="timezone"):
        resource(datetime(2026, 9, 21, 10))


def test_sample_availability_never_becomes_live_even_when_fresh():
    now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    item = resource(now).model_copy(update={"is_sample": True})
    assert safe_availability(item, now) == Availability.UNKNOWN
