"""The "open now" filter reaches SMS senders in all three languages.

find_resources has always been able to filter to resources whose hours can
honestly be called open (never samples, never stale data), but only API
callers could ask. A person texting at 2 AM needs it most. The modifier uses
the same reviewed words the replies already use for the open status - "open
(now)", "abierto/abierta", "furan" - and, like category words, the
non-English spellings demonstrate the sender's language. No new wording: an
open-now search over sample data answers with the existing no-results reply,
because sample hours must never be presented as live.
"""
import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import main
from app.data import load_resources
from app.i18n import Language
from app.models import ResourceCategory
from app.sms import parse_sms


@pytest.mark.parametrize("body,location,category,language", [
    ("open shelter 55415", "55415", ResourceCategory.SHELTER, Language.ENGLISH),
    ("shelter open now 55415", "55415", ResourceCategory.SHELTER, Language.ENGLISH),
    ("open 55415", "55415", None, Language.ENGLISH),
    ("abierto refugio 55415", "55415", ResourceCategory.SHELTER, Language.SPANISH),
    ("abierta ducha 55103", "55103", ResourceCategory.SHOWER, Language.SPANISH),
    ("furan cunto 55103", "55103", ResourceCategory.MEAL, Language.SOMALI),
    ("furan 55103", "55103", None, Language.SOMALI),
])
def test_open_now_modifier_parses_in_every_language(body, location, category, language):
    query = parse_sms(body)
    assert query is not None
    assert query.location == location
    assert query.category is category
    assert query.language is language
    assert query.open_now


def test_plain_queries_do_not_filter():
    query = parse_sms("shelter 55415")
    assert query is not None
    assert not query.open_now


def test_the_modifier_does_not_corrupt_the_place():
    query = parse_sms("shelter open now minneapolis")
    assert query is not None
    assert query.location == "minneapolis"
    assert query.open_now


def test_an_english_word_still_vetoes_the_language_guess():
    query = parse_sms("abierto shelter 55415")
    assert query is not None
    assert query.language is Language.ENGLISH
    assert query.open_now


def sms_reply(client, body, sender):
    response = client.post("/sms", data={"Body": body, "From": sender})
    assert response.status_code == 200
    return re.search(r"<Message>(.*?)</Message>", response.text, re.S).group(1)


def test_open_now_never_presents_sample_hours_as_live():
    # Every listing in the dev directory is a sample: an open-now search must
    # answer with the no-results reply, not with sample hours dressed as live.
    client = TestClient(main.app)
    reply = sms_reply(client, "open shelter 55415", "+15555550601")
    assert "No matching resources found" in reply
    assert "211" in reply and "911" in reply
    assert "Sample" not in reply


def test_open_now_spanish_sender_gets_the_spanish_no_results_reply():
    client = TestClient(main.app)
    reply = sms_reply(client, "abierto refugio 55415", "+15555550602")
    assert "No encontré recursos" in reply
    assert "211" in reply and "911" in reply


def test_a_fresh_verified_listing_answers_open_now(monkeypatch):
    always_open = {day: [("00:00", "24:00")] for day in range(7)}
    real = load_resources()[0].model_copy(update={
        "is_sample": False,
        "verified_at": datetime.now(timezone.utc),
        "hours": always_open,
    })
    monkeypatch.setattr(main, "resources", [real])
    client = TestClient(main.app)
    reply = sms_reply(client, "open shelter 55415", "+15555550603")
    assert "Nearest resources" in reply
    assert ", open," in reply
