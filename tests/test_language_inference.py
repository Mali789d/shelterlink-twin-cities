"""Reply in the language the sender demonstrably used.

The HELP reply explains the "lang es" directive in English, so a monolingual
Spanish or Somali speaker cannot learn it from a message they cannot read.
When every category word in the message belongs to one non-English language,
the reviewed templates in that language answer instead. Explicit signals
("lang en", "english") always win, and one English word or words from two
languages veto the guess - the same conservative shape as the bare "es"/"so"
code guard.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.i18n import Language
from app.main import app
from app.sms import detect_language, parse_sms


@pytest.mark.parametrize("body,language", [
    ("comida 55415", Language.SPANISH),
    ("refugio minneapolis", Language.SPANISH),
    ("ducha 55103", Language.SPANISH),
    ("centro de calor 55411", Language.SPANISH),
    ("cunto 55103", Language.SOMALI),
    ("qubays frogtown", Language.SOMALI),
    ("hoy 55401", Language.SOMALI),
    ("meel diirran 55411", Language.SOMALI),
    ("comida", Language.SPANISH),   # no location: the help reply still matches
    ("cunto", Language.SOMALI),
])
def test_category_words_infer_the_reply_language(body, language):
    assert detect_language(body) is language
    query = parse_sms(body)
    if query is not None:
        assert query.language is language


@pytest.mark.parametrize("body", [
    "comida 55415 lang:en",
    "comida 55415 english",
    "food 55415",               # English words never trigger a guess
    "shelter comida 55415",     # one English word vetoes
    "comida cunto 55415",       # two languages veto
    "es 55415",                 # a bare code is not a category word
    "55415",                    # no category words at all
    "minneapolis",
])
def test_english_is_kept_when_the_guess_is_not_unambiguous(body):
    assert detect_language(body) is Language.ENGLISH


@pytest.mark.parametrize("body,language", [
    ("comida 55415 lang en", Language.ENGLISH),
    ("cunto 55103 lang es", Language.SPANISH),
    ("cunto 55103 lang:es", Language.SPANISH),
])
def test_an_explicit_signal_wins_over_the_category_words(body, language):
    # The directive and the category words may point at different languages;
    # the explicit ask is always honored.
    assert detect_language(body) is language


def sms_reply(client, body, sender):
    response = client.post("/sms", data={"Body": body, "From": sender})
    assert response.status_code == 200
    return re.search(r"<Message>(.*?)</Message>", response.text, re.S).group(1)


def test_spanish_sender_gets_spanish_results_without_a_directive():
    client = TestClient(app)
    reply = sms_reply(client, "comida 55415", "+15555550401")
    assert "Recursos más cercanos" in reply
    assert "211" in reply and "911" in reply


def test_somali_sender_gets_somali_results_without_a_directive():
    client = TestClient(app)
    reply = sms_reply(client, "cunto 55103", "+15555550402")
    assert "Adeegyada kuugu dhow" in reply
    assert "211" in reply and "911" in reply


def test_category_only_message_gets_the_matching_help_reply():
    # "comida" alone has no location, but the help reply still answers in the
    # sender's language instead of English they demonstrably may not read.
    client = TestClient(app)
    reply = sms_reply(client, "comida", "+15555550403")
    assert "Envía un código postal" in reply
    reply = sms_reply(client, "cunto", "+15555550404")
    assert "Soo dir ZIP" in reply


def test_unknown_location_reply_uses_the_inferred_language():
    client = TestClient(app)
    reply = sms_reply(client, "comida nowhereville", "+15555550405")
    assert "No encontré ese lugar" in reply
