"""A geocoder outage or malformed result must not turn into a webhook 500.

Twilio retries 5xx responses, so an uncontained geocoder failure delays or drops
the reply entirely. The webhook answers with the localized safety reply instead.
"""
import pytest
from fastapi.testclient import TestClient

from html import escape

import app.main as main
from app.i18n import MESSAGES, Language


class RaisingGeocoder:
    def geocode(self, location):
        raise ConnectionError("geocoder unreachable")


class BadResultGeocoder:
    def __init__(self, result):
        self.result = result

    def geocode(self, location):
        return self.result


def post_sms(body="55415 shelter"):
    return TestClient(main.app).post(
        "/sms", data={"Body": body, "From": "+15555550113"})


def assert_safe_reply(response, language=Language.ENGLISH):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert escape(MESSAGES[language]["unknown_location"]) in response.text
    assert "211" in response.text and "911" in response.text


def test_raising_geocoder_gets_localized_safety_reply(monkeypatch):
    monkeypatch.setattr(main, "geocoder", RaisingGeocoder())
    assert_safe_reply(post_sms())


@pytest.mark.parametrize("result", [
    (float("nan"), -93.0),
    (91.0, 0.0),
    (-90.1, 181.0),
    ("44.9", "-93.1"),
    "55415",
    (44.9,),
])
def test_malformed_geocoder_results_get_safety_reply(monkeypatch, result):
    monkeypatch.setattr(main, "geocoder", BadResultGeocoder(result))
    assert_safe_reply(post_sms())


def test_geocoder_failure_preserves_reply_language(monkeypatch):
    monkeypatch.setattr(main, "geocoder", RaisingGeocoder())
    assert_safe_reply(post_sms("55415 shelter lang es"), Language.SPANISH)
    assert_safe_reply(post_sms("55415 hoy lang so"), Language.SOMALI)


def test_working_geocoder_still_returns_results(monkeypatch):
    monkeypatch.setattr(main, "geocoder", BadResultGeocoder((44.9778, -93.2650)))
    response = post_sms()
    assert response.status_code == 200
    assert MESSAGES[Language.ENGLISH]["heading"] in response.text
