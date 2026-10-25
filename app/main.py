import json
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request, Response

from .data import load_resources
from .geocoding import DevelopmentGeocoder, parse_coordinates
from .i18n import MESSAGES, Language, parse_language
from .idempotency import ReplyCache
from .keywords import (
    InMemoryOptOutStore, Keyword, OptOutStore, classify_keyword, durable_opt_out_store,
)
from .legal import PRIVACY, TERMS, notice_page
from .models import ResourceCategory, ResourceResult
from .search import find_resources, validate_coordinates
from .readiness import readiness_checks
from .security import Verdict, WebhookSecurity
from .sms import format_results, parse_sms, twiml
from .throttle import ReplyThrottle
from .webhook_form import read_sms_form

app = FastAPI(
    title="ShelterLink Twin Cities",
    description="SMS-first nearby resource finder for people experiencing homelessness.",
    version="0.1.0",
)
resources = load_resources()
geocoder = DevelopmentGeocoder()
opt_outs = InMemoryOptOutStore()
reply_throttle = ReplyThrottle.from_env()
reply_cache = ReplyCache()


def get_opt_out_store() -> OptOutStore:
    if os.environ.get("SHELTERLINK_ENV", "").strip().lower() != "production":
        return opt_outs
    return durable_opt_out_store(
        os.environ.get("OPT_OUT_TABLE", ""), os.environ.get("OPT_OUT_HASH_SALT", ""),
    )


def prototype_data_only() -> bool:
    """Production may not expose fixtures as a real nearby-resource directory."""
    return os.environ.get("SHELTERLINK_ENV", "").strip().lower() == "production" and (
        not resources or any(item.is_sample for item in resources)
    )


@app.get("/privacy", include_in_schema=False)
def privacy():
    return notice_page("Privacy", PRIVACY)


@app.get("/terms", include_in_schema=False)
def terms():
    return notice_page("Terms", TERMS)


@app.get("/health")
def health() -> dict[str, str | int]:
    return {"status": "ok", "resources": len(resources)}


@app.get("/ready")
def ready():
    checks = readiness_checks(resources, geocoder, os.environ, datetime.now(timezone.utc))
    # No network probes, phone numbers, resource addresses, table names or secrets.
    return Response(
        content=json.dumps({
            "status": "configuration_ready" if all(checks.values()) else "not_ready",
            "checks": checks,
            "external_dependencies_verified": False,
        }),
        status_code=200 if all(checks.values()) else 503,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def resolve_search_coordinates(lat: float | None, lon: float | None,
                               location: str | None) -> tuple[float, float]:
    """Exactly one coordinate source: an explicit pair, a "lat, lng"
    string, or a known place - never a guess."""
    if location is not None and not location.strip():
        raise HTTPException(status_code=400, detail="Location must not be blank")
    if location and (lat is not None or lon is not None):
        raise HTTPException(status_code=400,
                            detail="Pass either coordinates or a location, not both")
    if location:
        coordinates = parse_coordinates(location)
        if coordinates is not None:
            return coordinates
        try:
            coordinates = geocoder.geocode(location)
            if coordinates is not None:
                validate_coordinates(*coordinates)
        except Exception:
            # A broken geocoder is a server misconfiguration, not a bad request.
            # Do not log exceptions here: provider errors can contain request data.
            raise HTTPException(status_code=503, detail="Location lookup is unavailable")
        if coordinates is None:
            raise HTTPException(status_code=400, detail="Unknown location")
        return coordinates
    if (lat is None) != (lon is None):
        raise HTTPException(status_code=400, detail="lat and lon must come together")
    if lat is None:
        raise HTTPException(status_code=400, detail="Pass coordinates or a location")
    return lat, lon


@app.get("/resources/search", response_model=list[ResourceResult])
def search_resources(
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    location: str | None = Query(default=None, max_length=100),
    category: ResourceCategory | None = None,
    open_now: bool = False,
    limit: int = Query(default=3, ge=1, le=10),
    radius_miles: float | None = Query(default=None, ge=0, allow_inf_nan=False),
) -> list[ResourceResult]:
    coordinates = resolve_search_coordinates(lat, lon, location)
    if prototype_data_only():
        raise HTTPException(status_code=503, detail="Verified resource data is not available")
    return find_resources(resources, *coordinates, category, open_now, limit,
                          radius_miles=radius_miles)


@app.post("/sms")
async def sms(request: Request) -> Response:
    form = await read_sms_form(request)
    message_sid = str(form.get("MessageSid") or "")
    if message_sid:
        cached = reply_cache.get(message_sid)
        if cached is not None:
            # A Twilio redelivery of a message we already answered: replay the
            # identical response instead of sending a second paid reply.
            return Response(cached, media_type="application/xml")
    response = respond_to_sms_form(request, form)
    if message_sid and response.status_code == 200:
        # Only successful replies are cached: a redelivery after a 4xx/5xx is
        # processed fresh so the sender still gets help once the outage clears.
        reply_cache.put(message_sid, response.body.decode("utf-8"))
    return response


def respond_to_sms_form(request: Request, form) -> Response:
    params = {key: form.getlist(key) for key in form.keys()}
    verdict = WebhookSecurity.from_env().check(
        str(request.url), params, request.headers.get("X-Twilio-Signature")
    )
    if verdict is Verdict.REJECT:
        return Response("Invalid Twilio signature", status_code=403, media_type="text/plain")
    if verdict is Verdict.MISCONFIGURED:
        return Response("SMS webhook is not configured", status_code=503, media_type="text/plain")

    body = str(form.get("Body") or "")
    sender = str(form.get("From") or "")
    if not sender:
        return Response("SMS sender is required", status_code=400, media_type="text/plain")
    keyword = classify_keyword(body)
    try:
        store = get_opt_out_store()
        if keyword:
            kind, keyword_language = keyword
            if kind is Keyword.OPT_OUT:
                store.opt_out(sender)
                return Response(twiml(None), media_type="application/xml")
            if kind is Keyword.OPT_IN:
                store.opt_in(sender)
                return Response(twiml(MESSAGES[Language.ENGLISH]["opt_in"]), media_type="application/xml")
            return Response(twiml(MESSAGES[keyword_language]["help"]), media_type="application/xml")
        if store.is_opted_out(sender):
            return Response(twiml(None), media_type="application/xml")
    except Exception:
        # Never acknowledge START or send a referral if consent storage is unavailable.
        # Do not log exceptions here: provider errors can contain request data.
        return Response("SMS consent storage is unavailable", status_code=503, media_type="text/plain")

    if not reply_throttle.allow(sender):
        # Past the per-sender reply budget: empty TwiML ends the exchange with
        # no outbound message, so a runaway sender cannot run up reply charges.
        return Response(twiml(None), media_type="application/xml")

    language = parse_language(body)
    if prototype_data_only():
        return Response(twiml(MESSAGES[language]["not_live"]), media_type="application/xml")
    query = parse_sms(body)
    if not query:
        message = MESSAGES[language]["help"]
    else:
        try:
            coordinates = parse_coordinates(query.location)
            if coordinates is None:
                coordinates = geocoder.geocode(query.location)
            if coordinates is not None:
                validate_coordinates(*coordinates)
        except Exception:
            # A geocoder outage or malformed result must not become a webhook 500:
            # Twilio retries 5xx and the sender receives no guidance at all.
            # Do not log exceptions here: provider errors can contain request data.
            coordinates = None
        if not coordinates:
            message = MESSAGES[query.language]["unknown_location"]
        else:
            found = find_resources(resources, *coordinates, category=query.category, limit=3)
            message = format_results(found, query.language)
    return Response(twiml(message), media_type="application/xml")
