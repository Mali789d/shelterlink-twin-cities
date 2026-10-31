from datetime import datetime
from math import asin, cos, isfinite, radians, sin, sqrt
from zoneinfo import ZoneInfo

from .freshness import Freshness, resource_freshness, safe_availability
from .models import Resource, ResourceCategory, ResourceResult

TWIN_CITIES_TZ = ZoneInfo("America/Chicago")


def validate_coordinates(latitude: float, longitude: float) -> None:
    if (isinstance(latitude, bool) or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float))
            or not isfinite(latitude) or not isfinite(longitude)
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        raise ValueError("coordinates must be finite latitude/longitude within bounds")


def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two coordinates."""
    validate_coordinates(lat1, lon1)
    validate_coordinates(lat2, lon2)
    radius_miles = 3958.7613
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_miles * asin(sqrt(min(1.0, max(0.0, a))))


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
    radius_miles: float | None = None,
) -> list[ResourceResult]:
    validate_coordinates(lat, lon)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError("limit must be an integer from 1 through 10")
    if radius_miles is not None and (isinstance(radius_miles, bool)
            or not isinstance(radius_miles, (int, float))
            or not isfinite(radius_miles) or radius_miles < 0):
        raise ValueError("radius must be finite and nonnegative")
    observed_at = at or datetime.now(TWIN_CITIES_TZ)
    matches = []
    for resource in resources:
        # A schedule alone cannot prove a site is currently open. Never present old
        # or sample hours as live, even when the recorded clock range includes now.
        fresh = resource_freshness(resource, observed_at)
        opened = (
            not resource.is_sample
            and fresh is Freshness.CURRENT
            and is_open(resource, observed_at)
        )
        if category and resource.category != category:
            continue
        if open_now and not opened:
            continue
        distance = distance_miles(lat, lon, resource.latitude, resource.longitude)
        if radius_miles is not None and distance > radius_miles:
            continue
        matches.append((distance,
            ResourceResult(
                resource=resource,
                distance_miles=round(distance, 1),
                open_now=opened,
                availability=safe_availability(resource, observed_at),
                data_freshness=fresh.value,
            )
        ))
    # Round for display only: ranking rounded miles can hide the nearest resource.
    # Co-located services (a shelter and a meal program at one address) tie on
    # every nearby search; break ties by id, exactly like web/directory.mjs
    # nearbyResources, so the SMS reply, the API and the static page always
    # present - and cut at the limit - the same deterministic order no matter
    # how the data file happens to be ordered.
    return [item for _, item in sorted(
        matches, key=lambda pair: (pair[0], pair[1].resource.id))[:limit]]
