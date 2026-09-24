import base64
import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import Verdict, WebhookSecurity, compute_signature, is_valid_signature

TOKEN = "test-auth-token"
client = TestClient(app)


def reference_signature(token: str, payload: str) -> str:
    digest = hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def test_signature_concatenates_url_and_sorted_params():
    params = {"To": "+18005551212", "Body": "55415 shelter", "From": "+16125550100"}
    expected = reference_signature(
        TOKEN,
        "https://example.org/sms" + "Body55415 shelter" + "From+16125550100" + "To+18005551212",
    )
    assert compute_signature(TOKEN, "https://example.org/sms", params) == expected


def test_repeated_params_are_signed_in_sorted_order():
    expected = reference_signature(TOKEN, "https://example.org/smsMediaUrla" + "MediaUrlb")
    assert compute_signature(TOKEN, "https://example.org/sms", {"MediaUrl": ["b", "a"]}) == expected


def test_default_port_variants_are_accepted():
    params = {"Body": "hi"}
    signed_with_port = compute_signature(TOKEN, "https://example.org:443/sms", params)
    assert is_valid_signature(TOKEN, "https://example.org/sms", params, signed_with_port)
    signed_without_port = compute_signature(TOKEN, "https://example.org/sms", params)
    assert is_valid_signature(TOKEN, "https://example.org:443/sms", params, signed_without_port)


def test_missing_or_wrong_signature_is_rejected():
    params = {"Body": "hi"}
    assert not is_valid_signature(TOKEN, "https://example.org/sms", params, None)
    wrong = compute_signature("other-token", "https://example.org/sms", params)
    assert not is_valid_signature(TOKEN, "https://example.org/sms", params, wrong)


def test_public_base_url_replaces_internal_origin():
    security = WebhookSecurity(TOKEN, "https://abc.execute-api.us-east-2.amazonaws.com/", False)
    assert (
        security.signed_url("http://127.0.0.1:8000/sms?x=1")
        == "https://abc.execute-api.us-east-2.amazonaws.com/sms?x=1"
    )


def test_production_without_token_fails_closed():
    security = WebhookSecurity.from_env({"SHELTERLINK_ENV": "production"})
    assert security.check("https://example.org/sms", {}, None) is Verdict.MISCONFIGURED


def test_development_without_token_allows_local_testing():
    assert WebhookSecurity.from_env({}).check("http://testserver/sms", {}, None) is Verdict.ACCEPT


@pytest.fixture
def signed_env(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://sms.shelterlink.example")


def test_sms_webhook_accepts_valid_twilio_signature(signed_env):
    data = {"Body": "55415 shelter", "From": "+16125550100"}
    signature = compute_signature(TOKEN, "https://sms.shelterlink.example/sms", data)
    response = client.post("/sms", data=data, headers={"X-Twilio-Signature": signature})
    assert response.status_code == 200
    assert "Nearest resources" in response.text


def test_sms_webhook_rejects_tampered_body(signed_env):
    signature = compute_signature(TOKEN, "https://sms.shelterlink.example/sms", {"Body": "55415 shelter"})
    response = client.post("/sms", data={"Body": "55415 meal"}, headers={"X-Twilio-Signature": signature})
    assert response.status_code == 403


def test_sms_webhook_rejects_unsigned_request(signed_env):
    response = client.post("/sms", data={"Body": "55415 shelter"})
    assert response.status_code == 403


def test_sms_webhook_returns_503_when_production_secret_missing(monkeypatch):
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("SHELTERLINK_ENV", "production")
    response = client.post("/sms", data={"Body": "55415 shelter"})
    assert response.status_code == 503
