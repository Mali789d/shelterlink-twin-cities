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
- never label a site `open` from stale or sample opening hours;
- let data providers be replaced without changing the search and SMS layers.

## Current MVP

- FastAPI resource search endpoint
- distance ranking with a Haversine calculation
- category and `open_now` filters
- Twilio-compatible SMS webhook returning TwiML
- ZIP/location parsing behind a replaceable geocoder interface
- sample Twin Cities data marked as non-live
- automated unit and API tests
- English, Spanish, and Somali SMS responses using `lang en`, `lang es`, or `lang so`
- Twilio `X-Twilio-Signature` validation on the SMS webhook
- STOP/START/HELP keyword handling with hashed opt-out records
- plain HTML prototype privacy and terms notices at `/privacy` and `/terms`

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

## Webhook security

When `TWILIO_AUTH_TOKEN` is set, `/sms` only accepts requests carrying a valid
`X-Twilio-Signature` (HMAC-SHA1 over the public URL and sorted form parameters) and returns
`403` otherwise. This stops spoofed traffic from reaching the service or running up message
costs. Set `PUBLIC_BASE_URL` to the externally visible origin when running behind API Gateway
or another proxy, because Twilio signs the public URL. With `SHELTERLINK_ENV=production` and no
token configured, the webhook returns `503` instead of silently accepting unsigned requests.
Local development without a token accepts unsigned requests so the curl example works.

## Opt-out and help keywords

A message that is only an opt-out word (`STOP`, `STOPALL`, `UNSUBSCRIBE`, `CANCEL`, `END`,
`QUIT`, `REVOKE`, `OPTOUT`, `PARAR`, `JOOJI`) records the opt-out and gets an empty TwiML
response, and that number gets no further replies until it texts `START`, `UNSTOP`, or `YES`.
Twilio's standard opt-out handling sends the carrier confirmation. `HELP`/`INFO`, `AYUDA`, and
`CAAWIMO` return program info and opt-out instructions in English, Spanish, or Somali, and
they still work after an opt-out. Keywords match only when they are the whole message, so a
search like `55415 end` still runs.

Phone numbers are stored only as salted SHA-256 digests (`OPT_OUT_HASH_SALT`). The current
store lives in memory and is lost on restart. A persistent store is required before public
launch.

## Public notices

`/privacy` and `/terms` are plain, accessible pre-launch pages. They explicitly say the
service is a prototype without a public SMS number, and that sample listings are not
current referrals. Before offering a public SMS number, review both notices against
the actual Twilio/AWS configuration, retention, provider data and support contact.
Publishing a prototype notice alone does not finish toll-free verification or make
the service safe to launch.

## AWS Lambda packaging (not deployed)

`template.yaml` defines an API Gateway HTTP API and Python Lambda handler using Mangum.
The explicit routes are `/health`, `/resources/search`, `/privacy`, `/terms`, and `/sms`.
`tests/test_lambda.py` runs HTTP API v2 events through the handler, including signed and
unsigned SMS. AWS SAM builds dependencies from `requirements.txt` at the `CodeUri`.
No AWS stack or public number has been created. In production mode, sample data makes
`/resources/search` return 503 and a valid SMS search returns a 211/911 guidance
message rather than a sample listing. STOP/START/HELP still work. Do not deploy for
public use yet: the
resource data and ZIP geocoder are development fixtures, opt-outs are not persistent,
and the privacy/terms notices lack final hosting and contact details. The template sets
`SHELTERLINK_ENV=production`, so `/sms` returns 503 without a Twilio auth token.
Before deployment, securely provide the token and `PUBLIC_BASE_URL` matching the
actual API URL, ensure durable opt-outs, verified resource data, and cost approval.

## Safety and data quality

A directory can cause harm if it presents old hours or guessed bed availability as current. Every
resource record therefore carries its source, last verification time, and availability status.
Unknown availability stays unknown. The `open_now` filter excludes sample and stale hours,
and SMS uses `hours vary` instead of `open` when hours have not been freshly verified.
The first production release will add official/provider data,
expiration rules, and a human correction path before any public launch.

## Roadmap

- [x] Normalized resource model and proximity search
- [x] SMS webhook and compact replies
- [x] Tests for ranking, filters, parsing, and TwiML
- [ ] Import verified Minneapolis, Hennepin County, Saint Paul, Ramsey County, and 211 resources
- [x] Add a 24-hour freshness policy that downgrades stale availability to unknown
- [ ] Add provider-reported availability feeds
- [ ] Add scheduled ingestion, deduplication, and change history
- [x] Validate Twilio webhook signatures
- [x] Handle STOP/START/HELP keywords
- [ ] Persist opt-outs in a durable store
- [x] Package API Gateway HTTP API and Lambda handler with local smoke tests
- [ ] Deploy API and SMS webhook on AWS
- [ ] Build an outreach-worker dashboard
- [x] Add Spanish and Somali response templates
- [ ] Add Hmong response templates and community language review
