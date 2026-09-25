import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.i18n import Language
from app.keywords import InMemoryOptOutStore, Keyword, classify_keyword, hash_phone

client = TestClient(main.app)
EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    monkeypatch.setattr(main, "opt_outs", InMemoryOptOutStore(salt="test"))


@pytest.mark.parametrize("body", ["STOP", "stop", " Stop. ", "UNSUBSCRIBE", "quit", "Revoke", "opt out", "parar"])
def test_opt_out_words(body):
    assert classify_keyword(body) == (Keyword.OPT_OUT, Language.ENGLISH)


def test_keywords_only_match_whole_message():
    assert classify_keyword("55415 end") is None
    assert classify_keyword("stop by shelter 55415") is None


def test_help_keyword_picks_language():
    assert classify_keyword("HELP") == (Keyword.HELP, Language.ENGLISH)
    assert classify_keyword("ayuda") == (Keyword.HELP, Language.SPANISH)
    assert classify_keyword("Caawimo") == (Keyword.HELP, Language.SOMALI)


def test_store_hashes_numbers():
    store = InMemoryOptOutStore(salt="s")
    store.opt_out("+1 (612) 555-0100")
    assert store.is_opted_out("+16125550100")
    assert "6125550100" not in "".join(store.stored_digests())
    assert hash_phone("+16125550100", "a") != hash_phone("+16125550100", "b")


def sms(body, sender="+16125550100"):
    return client.post("/sms", data={"Body": body, "From": sender})


def test_stop_silences_all_later_replies_for_that_number():
    assert sms("STOP").text == EMPTY
    assert sms("55415 shelter").text == EMPTY
    assert "Nearest resources" in sms("55415 shelter", sender="+16125550199").text


def test_start_resumes_replies():
    sms("STOP")
    started = sms("START")
    assert "subscribed again" in started.text
    assert "Nearest resources" in sms("55415 shelter").text


def test_help_returns_program_info_instead_of_location_error():
    response = sms("HELP")
    assert "ShelterLink Twin Cities" in response.text
    assert "Reply STOP to opt out" in response.text
    assert "couldn" not in response.text


def test_help_still_answers_after_opt_out():
    sms("STOP")
    assert "ShelterLink" in sms("help").text


def test_spanish_and_somali_help_include_opt_out():
    assert "Responde STOP" in sms("AYUDA").text
    assert "Ku jawaab STOP" in sms("caawimo").text
