"""Offline readiness checks, not an assertion of verified live dependencies."""
from datetime import datetime

from .freshness import Freshness, resource_freshness
from .geocoding import DevelopmentGeocoder
from .models import Resource
from .security import WebhookSecurity, valid_public_origin


def readiness_checks(resources: list[Resource], geocoder, env, at: datetime) -> dict[str, bool]:
    security = WebhookSecurity.from_env(env)
    # Readiness is callable outside startup; copied models can bypass validation.
    try:
        checked = [Resource.model_validate(item.model_dump()) for item in resources]
        unique = len({item.id for item in checked}) == len(checked)
        valid = bool(checked) and unique
        verified = valid and all(not item.is_sample for item in checked)
        current = valid and all(
            resource_freshness(item, at) is Freshness.CURRENT for item in checked
        )
    except (ValueError, TypeError, AttributeError):
        verified = current = False
    return {
        "production_mode": env.get("SHELTERLINK_ENV", "").strip().lower() == "production",
        "verified_resource_snapshot": verified,
        "current_resource_snapshot": current,
        "twilio_token_configured": bool(security.auth_token),
        "public_https_origin": valid_public_origin(security.public_base_url, require_https=True),
        "durable_consent_configured": bool(env.get("OPT_OUT_TABLE", "").strip())
            and len(env.get("OPT_OUT_HASH_SALT", "").strip()) >= 32,
        "production_geocoder": callable(getattr(geocoder, "geocode", None))
            and not isinstance(geocoder, DevelopmentGeocoder),
    }
