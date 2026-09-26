"""Plain, accessible pre-launch notices for the prototype.

These pages describe the actual current service, not a live shelter directory or a
finished SMS program. Revise them against production infrastructure before launch.
"""

from html import escape

from fastapi.responses import HTMLResponse


def notice_page(title: str, sections: list[tuple[str, str]]) -> HTMLResponse:
    items = "\n".join(
        f"<section><h2>{escape(heading)}</h2><p>{escape(body)}</p></section>"
        for heading, body in sections
    )
    page = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)} | ShelterLink Twin Cities</title>"
        "<style>body{max-width:44rem;margin:2rem auto;padding:0 1rem;"
        "font:1.1rem/1.6 system-ui,sans-serif}a{color:#0645ad}"
        "</style></head><body><main>"
        f"<h1>{escape(title)}</h1><p><strong>Prototype, not a live service.</strong> "
        "ShelterLink Twin Cities is in development. Do not rely on sample listings "
        "or bed availability for a trip. Call 211 for current local help; "
        "call 911 in an emergency.</p>"
        f"{items}<p><a href=\"/privacy\">Privacy</a> · "
        '<a href="/terms">Terms</a></p></main></body></html>'
    )
    return HTMLResponse(page)


PRIVACY = [
    (
        "What the prototype handles",
        "When someone sends a text to a future ShelterLink number, the SMS provider "
        "would receive the sender's phone number and message and send them to our webhook. "
        "The message can contain a ZIP code or location. The public prototype currently "
        "uses sample resource listings; it does not have a public SMS number yet.",
    ),
    (
        "How it is used",
        "The webhook uses the message to choose nearby sample listings and a language "
        "for its reply. It uses the sender's number to honor STOP and START. Its current "
        "in-memory opt-out list contains salted hashes of numbers, not the numbers themselves; "
        "that list disappears on restart and is not suitable for a public launch. "
        "The SMS provider may also retain messages and delivery records under its own policy.",
    ),
    (
        "Before launch",
        "A production deployment needs durable opt-outs, a documented log and data-retention "
        "policy, and verified resource data. This notice will be updated to reflect the "
        "actual hosting, providers, retention, and contact route before a public number is offered.",
    ),
]

TERMS = [
    (
        "Current status",
        "This is a development prototype, not a public emergency or referral service. "
        "Listings are samples and may not correspond to current services, hours, or bed openings. "
        "Do not travel based on these sample results. Call 211 for current local help "
        "and 911 in an emergency.",
    ),
    (
        "Future SMS use",
        "If an SMS line launches, standard carrier message and data rates may apply. "
        "STOP requests no further program replies, START resumes replies, and HELP gives "
        "program information. These terms must be reviewed with the final number, "
        "provider configuration, and privacy notice before public use.",
    ),
]
