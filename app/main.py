import os

from fastapi import FastAPI, HTTPException, Query, Request, Response

from .data import load_resources
from .geocoding import DevelopmentGeocoder
from .i18n import MESSAGES, Language, parse_language
from .keywords import (
    InMemoryOptOutStore, Keyword, OptOutStore, classify_keyword, durable_opt_out_store,
)
from .legal import PRIVACY, TERMS, notice_page
from .models import ResourceCategory, ResourceResult
from .search import find_resources
from .security import Verdict, WebhookSecurity
from .sms import format_results, parse_sms, twiml
from .webhook_form import read_sms_form

app = FastAPI(
    title="ShelterLink Twin Cities",
    description="SMS-first nearby resource finder for people experiencing homelessness.",
    version="0.1.0",
)
resources = load_resources()
geocoder = DevelopmentGeocoder()
opt_outs = InMemoryOptOutStore()


def get_opt_out_store() -> OptOutStore:
    if os.environ.get("SHELTERLINK_ENV", "").lower() != "production":
        return opt_outs
    return durable_opt_out_store(
        os.environ.get("OPT_OUT_TABLE", ""), os.environ.get("OPT_OUT_HASH_SALT", ""),
    )


def prototype_data_only() -> bool:
    """Production may not expose fixtures as a real nearby-resource directory."""
    return os.environ.get("SHELTERLINK_ENV", "").lower() == "production" and (
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


@app.get("/resources/search", response_model=list[ResourceResult])
def search_resources(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    category: ResourceCategory | None = None,
    open_now: bool = False,
    limit: int = Query(default=3, ge=1, le=10),
) -> list[ResourceResult]:
    if prototype_data_only():
        raise HTTPException(status_code=503, detail="Verified resource data is not available")
    return find_resources(resources, lat, lon, category, open_now, limit)


@app.post("/sms")
async def sms(request: Request) -> Response:
    form = await read_sms_form(request)
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

    language = parse_language(body)
    if prototype_data_only():
        return Response(twiml(MESSAGES[language]["not_live"]), media_type="application/xml")
    query = parse_sms(body)
    if not query:
        message = MESSAGES[language]["help"]
    else:
        coordinates = geocoder.geocode(query.location)
        if not coordinates:
            message = MESSAGES[query.language]["unknown_location"]
        else:
            found = find_resources(resources, *coordinates, category=query.category, limit=3)
            message = format_results(found, query.language)
    return Response(twiml(message), media_type="application/xml")
