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
  --data-urlencode 'Body=55415 shelter' \
  --data-urlencode 'From=+16125550100'
```

## SMS service vocabulary

The parser accepts the service terms advertised in each HELP reply: English
`shelter`/`bed`, `meal`/`food`, `warm`/`warming`, `shower`; Spanish `refugio`,
`comida`, `centro de calor`, `ducha`; Somali `hoy`, `cunto`, `meel diirran`, `qubays`.
These work with a ZIP or a supported named location, for example `55101 comida lang es`
or `Saint Paul cunto lang so`. Use an explicit language directive to choose the reply
language; service vocabulary alone does not select it.

Only whole words/phrases select a category, so a place like Bedford does not mean
`bed`. If a message includes multiple different service categories, the webhook returns
HELP instead of silently picking one. Send one service per search. Named locations still
use the small development geocoder, not a live geocoding service.

## Webhook security

When `TWILIO_AUTH_TOKEN` is set, `/sms` only accepts requests carrying a valid
`X-Twilio-Signature` (HMAC-SHA1 over the public URL and sorted form parameters) and returns
`403` otherwise. This stops spoofed traffic from reaching the service or running up message
costs. Set `PUBLIC_BASE_URL` to the externally visible origin when running behind API Gateway
or another proxy, because Twilio signs the public URL. With `SHELTERLINK_ENV=production` and no
token configured, the webhook returns `503` instead of silently accepting unsigned requests.
Production also requires an explicit HTTPS `PUBLIC_BASE_URL` origin. Credentials, paths,
query strings, fragments, whitespace, and invalid ports are rejected as configuration
errors before consent storage is touched. The request Host header is never a substitute
for that configured production origin. Invalid/non-ASCII signatures return rejection,
not a server error.
Local development without a token accepts unsigned requests so the curl example works.

The SMS endpoint accepts only `application/x-www-form-urlencoded` requests. It reads
at most 16 KiB, including streamed requests without a Content-Length, and at most 64
form fields. Invalid UTF-8/percent escapes and duplicate Body/From/To/message/account
identity fields are rejected before signature and consent processing. Repeated
noncritical fields remain supported and all values participate in signature validation.
Limits apply to inbound metadata, not just the user's text. Multipart uploads and JSON
are not SMS webhook inputs. These limits bound application parsing work; they do not
replace gateway throttling or upstream traffic-cost controls.

## Opt-out and help keywords

A message that is only an opt-out word (`STOP`, `STOPALL`, `UNSUBSCRIBE`, `CANCEL`, `END`,
`QUIT`, `REVOKE`, `OPTOUT`, `PARAR`, `JOOJI`) records the opt-out and gets an empty TwiML
response, and that number gets no further replies until it texts `START`, `UNSTOP`, or `YES`.
Twilio's standard opt-out handling sends the carrier confirmation. `HELP`/`INFO`, `AYUDA`, and
`CAAWIMO` return program info and opt-out instructions in English, Spanish, or Somali, and
they still work after an opt-out. Keywords match only when they are the whole message, so a
search like `55415 end` still runs.

Phone numbers are stored only as salted SHA-256 digests (`OPT_OUT_HASH_SALT`).
Development uses process-local memory. Production requires `OPT_OUT_TABLE` and a private,
unchanging `OPT_OUT_HASH_SALT` of at least 32 characters, and uses DynamoDB with strongly consistent reads. Only the
digest is saved, with no message body or automatic expiry. STOP survives separate Lambda
instances; START deletes the digest. Missing configuration or a failed storage operation
returns 503 without a message, never an in-memory fallback or a false START confirmation.
An SMS without a sender is rejected. Changing the salt or table loses lookup continuity:
preserve both across deployments and treat any migration as a consent-data migration.
Local stubbed AWS API and shared-backend tests cover this contract; no AWS table exists yet.

## Public notices

`/privacy` and `/terms` are plain, accessible pre-launch pages. They explicitly say the
service is a prototype without a public SMS number, and that sample listings are not
current referrals. Before offering a public SMS number, review both notices against
the actual Twilio/AWS configuration, retention, provider data and support contact.
Publishing a prototype notice alone does not finish toll-free verification or make
the service safe to launch.

## AWS Lambda packaging (not deployed)

`template.yaml` defines an API Gateway HTTP API and Python Lambda handler using Mangum.
The explicit routes are `/health`, `/ready`, `/resources/search`, `/privacy`, `/terms`, and `/sms`.
`tests/test_lambda.py` runs HTTP API v2 events through the handler, including signed and
unsigned SMS. AWS SAM builds dependencies from `requirements.txt` at the `CodeUri`.
No AWS stack or public number has been created. In production mode, sample data makes
`/resources/search` return 503 and a valid SMS search returns a 211/911 guidance
message rather than a sample listing when consent storage is configured. STOP/START/HELP
use the durable store in production. Do not deploy for
public use yet: the
resource data and ZIP geocoder are development fixtures, durable opt-outs are not deployed,
and the privacy/terms notices lack final hosting and contact details. The template sets
`SHELTERLINK_ENV=production`, so `/sms` returns 503 without a Twilio auth token.
Before deployment, securely provide the token and `PUBLIC_BASE_URL` matching the
actual API URL, deploy and verify durable opt-outs, verified resource data, and cost approval.
The template prepares an encrypted DynamoDB table with 1 provisioned read/write capacity
unit and a retained-on-delete policy, plus only GetItem/PutItem/DeleteItem permissions.
It requires a private random salt of at least 32 characters. Never commit the salt or put
it in shell history. The retained table can continue to incur costs after stack deletion:
review account-specific pricing/free-tier eligibility and consent retention before deploy
or cleanup. This configuration is preparation, not a claim of a free or live deployment.

## Zero-cost directory preparation

The public SMS/AWS launch is on hold under a zero-cost requirement. A browser-based
static directory is an alternative under consideration, not an approved or published
replacement yet. The existing SMS code remains a prototype.

`python -m app.export_directory reviewed-resources.json directory.json` prepares a
static JSON snapshot without accounts, hosting, phone-number rental or paid services.
It rejects empty, sample, stale and future-dated input before touching the output.
Every exported listing retains its source and verification time; hours and availability
are deliberately excluded so the directory cannot be mistaken for a live bed feed.
The export is directory information only, with 211/911 guidance. Validation cannot
prove a provider was contacted: review input provenance separately. The bundled sample
file cannot be exported. No reviewed directory, site deployment or public number exists.
A later browser UI must recheck timestamps at view time; a successful export does not
keep a snapshot fresh forever.

## Liveness versus configuration readiness

`GET /health` is a process liveness check, not evidence that the service can safely
send referrals. `GET /ready` returns 503 until offline configuration checks pass:
production mode, a nonempty nonsample/current resource snapshot, Twilio token, trusted
HTTPS origin, durable-consent table/salt configuration, and a nondevelopment geocoder.
It returns only boolean checks, not secret values, table names, phone numbers or addresses,
and uses `Cache-Control: no-store`.

A 200 response means `configuration_ready`, not public-launch approval. The response
always states `external_dependencies_verified: false`: it does not contact AWS/Twilio,
verify resource provenance, test the phone line, or confirm the final notices/support
route. Run those checks separately before launching. The current bundled prototype
returns 503 for readiness even while health returns 200.

## Validated resource snapshots

`load_resources()` reads the development fixture by default. Set `SHELTERLINK_DATA_PATH`
to a reviewed JSON snapshot or pass a path directly to the loader. A snapshot must be
an array of records with unique IDs. The whole snapshot is rejected if any record is
invalid; there is no silent partial import. Verification timestamps must include a
timezone, and identity/address/source fields cannot be blank.

Records without `is_sample` default to `true`. Only explicitly reviewed records should
set it to `false`; that field is an operator assertion, not automatic provider verification.
Production continues to reject empty snapshots or any snapshot containing sample records.
Sample availability is always `unknown`, even with a fresh timestamp.

Weekly hours use weekday keys 0 (Monday) through 6 (Sunday), and zero-padded `HH:MM`
intervals. Start must be before end; `24:00` is allowed only as an end time. Represent
an overnight schedule as two intervals on adjacent weekdays, for example Monday
`22:00` to `24:00` and Tuesday `00:00` to `02:00`. End times are exclusive.
An invalid snapshot stops startup rather than falling back to an old or sample directory.
This loader does not fetch or verify provider data; the bundled records remain samples.

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
- [x] Implement DynamoDB opt-outs with local contract and failure tests
- [ ] Deploy and verify durable opt-outs across real Lambda instances
- [x] Package API Gateway HTTP API and Lambda handler with local smoke tests
- [ ] Deploy API and SMS webhook on AWS
- [ ] Build an outreach-worker dashboard
- [x] Add Spanish and Somali response templates
- [ ] Add Hmong response templates and community language review
