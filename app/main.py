from fastapi import FastAPI, Query, Request, Response

from .data import load_resources
from .geocoding import DevelopmentGeocoder
from .i18n import MESSAGES, Language, parse_language
from .keywords import InMemoryOptOutStore, Keyword, classify_keyword
from .models import ResourceCategory, ResourceResult
from .search import find_resources
from .security import Verdict, WebhookSecurity
from .sms import format_results, parse_sms, twiml

app = FastAPI(
    title="ShelterLink Twin Cities",
    description="SMS-first nearby resource finder for people experiencing homelessness.",
    version="0.1.0",
)
resources = load_resources()
geocoder = DevelopmentGeocoder()
opt_outs = InMemoryOptOutStore()


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
    return find_resources(resources, lat, lon, category, open_now, limit)


@app.post("/sms")
async def sms(request: Request) -> Response:
    form = await request.form()
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
    keyword = classify_keyword(body)
    if keyword:
        kind, keyword_language = keyword
        if kind is Keyword.OPT_OUT:
            opt_outs.opt_out(sender)
            return Response(twiml(None), media_type="application/xml")
        if kind is Keyword.OPT_IN:
            opt_outs.opt_in(sender)
            return Response(twiml(MESSAGES[Language.ENGLISH]["opt_in"]), media_type="application/xml")
        return Response(twiml(MESSAGES[keyword_language]["help"]), media_type="application/xml")
    if opt_outs.is_opted_out(sender):
        return Response(twiml(None), media_type="application/xml")

    language = parse_language(body)
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
