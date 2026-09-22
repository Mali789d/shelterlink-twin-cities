from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

from .freshness import resource_freshness, safe_availability
from .models import Resource, ResourceCategory, ResourceResult

TWIN_CITIES_TZ = ZoneInfo("America/Chicago")


def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two coordinates."""
    radius_miles = 3958.7613
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_miles * asin(sqrt(a))


def is_open(resource: Resource, at: datetime | None = None) -> bool:
    local = (at or datetime.now(TWIN_CITIES_TZ)).astimezone(TWIN_CITIES_TZ)
    current = local.strftime("%H:%M")
    for start, end in resource.hours.get(local.weekday(), []):
        if start <= current < end:
            return True
    return False


def find_resources(
    resources: list[Resource],
    lat: float,
    lon: float,
    category: ResourceCategory | None = None,
    open_now: bool = False,
    limit: int = 3,
    at: datetime | None = None,
) -> list[ResourceResult]:
    observed_at = at or datetime.now(TWIN_CITIES_TZ)
    matches = []
    for resource in resources:
        opened = is_open(resource, observed_at)
        if category and resource.category != category:
            continue
        if open_now and not opened:
            continue
        matches.append(
            ResourceResult(
                resource=resource,
                distance_miles=round(
                    distance_miles(lat, lon, resource.latitude, resource.longitude), 1
                ),
                open_now=opened,
                availability=safe_availability(resource, observed_at),
                data_freshness=resource_freshness(resource, observed_at).value,
            )
        )
    return sorted(matches, key=lambda item: item.distance_miles)[:limit]
