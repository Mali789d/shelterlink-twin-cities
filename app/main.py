from fastapi import FastAPI, Form, Query, Response

from .data import load_resources
from .geocoding import DevelopmentGeocoder
from .models import ResourceCategory, ResourceResult
from .search import find_resources
from .sms import format_results, parse_sms, twiml

app = FastAPI(
    title="ShelterLink Twin Cities",
    description="SMS-first nearby resource finder for people experiencing homelessness.",
    version="0.1.0",
)
resources = load_resources()
geocoder = DevelopmentGeocoder()


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
def sms(Body: str = Form(default="")) -> Response:
    query = parse_sms(Body)
    if not query:
        message = "Text a Twin Cities ZIP or location, optionally with shelter, meal, warming, or shower."
    else:
        coordinates = geocoder.geocode(query.location)
        if not coordinates:
            message = "I couldn't find that location yet. Try a 5-digit Twin Cities ZIP or call 211."
        else:
            found = find_resources(resources, *coordinates, category=query.category, limit=3)
            message = format_results(found)
    return Response(twiml(message), media_type="application/xml")
