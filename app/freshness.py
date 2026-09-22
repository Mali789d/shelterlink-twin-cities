from datetime import datetime, timedelta
from enum import Enum

from .models import Availability, Resource

DEFAULT_MAX_AGE = timedelta(hours=24)


class Freshness(str, Enum):
    CURRENT = "current"
    STALE = "stale"


def resource_freshness(
    resource: Resource,
    at: datetime,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> Freshness:
    """Classify source data by age without guessing that old data is current."""
    verified_at = resource.verified_at
    if verified_at.tzinfo is None or at.tzinfo is None:
        raise ValueError("freshness timestamps must include a timezone")
    age = at - verified_at
    return Freshness.CURRENT if timedelta(0) <= age <= max_age else Freshness.STALE


def safe_availability(
    resource: Resource,
    at: datetime,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> Availability:
    """Hide an availability claim after its source passes the freshness limit."""
    if resource_freshness(resource, at, max_age) == Freshness.STALE:
        return Availability.UNKNOWN
    return resource.availability
