"""Safety guidance must survive clarification, empty results and consent replies."""
import pytest
from fastapi.testclient import TestClient

from app.i18n import Language, MESSAGES
from app.main import app
from app.sms import format_results, twiml


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("kind", ["help", "opt_in", "unknown_location", "none", "not_live", "footer"])
def test_every_nonempty_reply_keeps_help_and_emergency_routes(language, kind):
    message = MESSAGES[language][kind]
    assert "211" in message and "911" in message
    if kind in {"help", "opt_in", "unknown_location", "none"}:
        assert message.endswith(MESSAGES[language]["footer"])


@pytest.mark.parametrize("language", list(Language))
def test_empty_results_use_localized_safety_footer(language):
    assert format_results([], language).endswith(MESSAGES[language]["footer"])


@pytest.mark.parametrize("body", ["HELP", "55415 or 55101", "unknownville", "START",
                                  "AYUDA", "CAAWIMO"])
def test_sms_paths_retain_both_routes(body):
    response = TestClient(app).post("/sms", data={"Body": body, "From": "+15555550113"})
    assert response.status_code == 200
    assert "211" in response.text and "911" in response.text


def test_stop_stays_empty_and_does_not_send_guidance():
    assert twiml(None).endswith("<Response></Response>")
    response = TestClient(app).post("/sms", data={"Body": "STOP", "From": "+15555550114"})
    assert response.status_code == 200
    assert "<Message>" not in response.text
