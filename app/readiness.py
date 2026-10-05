"""Offline readiness checks, not an assertion of verified live dependencies."""
from datetime import datetime

from .freshness import Freshness, resource_freshness
from .geocoding import DevelopmentGeocoder
from .models import Resource
from .security import WebhookSecurity, valid_public_origin


def readiness_checks(resources: list[Resource], geocoder, env, at: datetime) -> dict[str, bool]:
    security = WebhookSecurity.from_env(env)
    return {
        "production_mode": env.get("SHELTERLINK_ENV", "").lower() == "production",
        "verified_resource_snapshot": bool(resources) and all(not item.is_sample for item in resources),
        "current_resource_snapshot": bool(resources) and all(
            resource_freshness(item, at) is Freshness.CURRENT for item in resources
        ),
        "twilio_token_configured": bool(security.auth_token),
        "public_https_origin": valid_public_origin(security.public_base_url, require_https=True),
        "durable_consent_configured": bool(env.get("OPT_OUT_TABLE", "").strip())
            and len(env.get("OPT_OUT_HASH_SALT", "").strip()) >= 32,
        "production_geocoder": not isinstance(geocoder, DevelopmentGeocoder),
    }
