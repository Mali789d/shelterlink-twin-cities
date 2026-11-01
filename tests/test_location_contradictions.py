"""A ZIP and a contradictory named place must ask, never guess.

"shelter 55415 saint paul" names two known locations eight miles apart.
Answering for the ZIP alone sends a Saint Paul sender across town. Covered
places measure under two miles from their own ZIP's centroid; contradictory
pairs measure six or more, so the five-mile bound separates agreeing text
("55415 minneapolis") from contradictions with room to spare. Text that does
not resolve to a known place ("55415 please") never blocks the ZIP.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.geocoding import DevelopmentGeocoder
from app.main import app
from app.sms import parse_sms

GEOCODE = DevelopmentGeocoder().geocode


@pytest.mark.parametrize("body", [
    "shelter 55415 saint paul",
    "shelter 55103 minneapolis",
    "comida 55415 saint paul",
    "food near 55415 frogtown",
])
def test_contradictory_known_locations_ask_for_clarification(body):
    assert parse_sms(body, geocode=GEOCODE) is None


@pytest.mark.parametrize("body,zip_code", [
    ("shelter 55415 minneapolis", "55415"),      # the city the ZIP is in
    ("shelter 55415 near minneapolis", "55415"),  # a forgiven preposition too
    ("shelter 55103 frogtown", "55103"),          # the neighborhood the ZIP is
    ("shelter 55415 please", "55415"),            # unresolvable text is not a place
    ("shelter 55415 asap", "55415"),
    ("shelter 55415 near", "55415"),              # a lone preposition is not a place
])
def test_agreeing_or_unresolvable_text_keeps_the_zip(body, zip_code):
    query = parse_sms(body, geocode=GEOCODE)
    assert query is not None
    assert query.location == zip_code


def test_contradiction_check_needs_the_injected_resolver():
    # Without a resolver, parsing stays pure and keeps the historical behavior.
    query = parse_sms("shelter 55415 saint paul")
    assert query is not None
    assert query.location == "55415"


def test_a_geocoder_outage_falls_back_to_the_zip():
    def unavailable(_location):
        raise RuntimeError("geocoder down")
    query = parse_sms("shelter 55415 saint paul", geocode=unavailable)
    assert query is not None
    assert query.location == "55415"


def sms_reply(client, body, sender):
    response = client.post("/sms", data={"Body": body, "From": sender})
    assert response.status_code == 200
    return re.search(r"<Message>(.*?)</Message>", response.text, re.S).group(1)


def test_contradictory_message_gets_the_help_reply_not_resources():
    client = TestClient(app)
    reply = sms_reply(client, "shelter 55415 saint paul", "+15555550501")
    assert "Text a Twin Cities ZIP or location" in reply
    assert "Nearest resources" not in reply
    assert "Sample" not in reply


def test_contradictory_spanish_message_gets_the_spanish_help_reply():
    client = TestClient(app)
    reply = sms_reply(client, "comida 55415 saint paul", "+15555550502")
    assert "Envía un código postal" in reply
    assert "Nearest resources" not in reply


def test_agreeing_message_still_returns_results():
    client = TestClient(app)
    reply = sms_reply(client, "shelter 55415 minneapolis", "+15555550503")
    assert "Nearest resources" in reply
