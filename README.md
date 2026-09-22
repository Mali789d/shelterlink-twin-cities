# ShelterLink Twin Cities

An SMS-first resource finder for people experiencing homelessness in Minneapolis and Saint Paul.
A person can text a ZIP code or location and receive nearby shelters, free meals, warming spaces,
and showers without installing an app.

> Early development: the API and SMS response flow work with clearly labeled sample data. Live
> provider ingestion and availability verification are next. Never rely on this service for an
> emergency; call 911 for immediate danger and 211 for current local help.

## Why SMS

SMS works on basic phones, uses little data, and avoids an app install. The system is designed to:

- return a short, readable list rather than a map-heavy interface;
- show source and freshness so stale information is not presented as current;
- support multiple resource categories and cities through one normalized schema;
- expire availability claims after 24 hours so stale bed data becomes `unknown`;
- let data providers be replaced without changing the search and SMS layers.

## Current MVP

- FastAPI resource search endpoint
- distance ranking with a Haversine calculation
- category and `open_now` filters
- Twilio-compatible SMS webhook returning TwiML
- ZIP/location parsing behind a replaceable geocoder interface
- sample Twin Cities data marked as non-live
- automated unit and API tests

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for the API documentation.

## Test

```bash
pytest -q
```

## API

```bash
curl 'http://localhost:8000/resources/search?lat=44.9778&lon=-93.2650&category=shelter'

curl -X POST http://localhost:8000/sms \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'Body=55415 shelter'
```

## Safety and data quality

A directory can cause harm if it presents old hours or guessed bed availability as current. Every
resource record therefore carries its source, last verification time, and availability status.
Unknown availability stays unknown. The first production release will add official/provider data,
expiration rules, and a human correction path before any public launch.

## Roadmap

- [x] Normalized resource model and proximity search
- [x] SMS webhook and compact replies
- [x] Tests for ranking, filters, parsing, and TwiML
- [ ] Import verified Minneapolis, Hennepin County, Saint Paul, Ramsey County, and 211 resources
- [x] Add a 24-hour freshness policy that downgrades stale availability to unknown
- [ ] Add provider-reported availability feeds
- [ ] Add scheduled ingestion, deduplication, and change history
- [ ] Deploy API and SMS webhook on AWS
- [ ] Build an outreach-worker dashboard
- [ ] Add Spanish, Somali, and Hmong response templates
