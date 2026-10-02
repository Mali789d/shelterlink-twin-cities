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


@pytest.mark.parametrize("origin", [
    None, "", "http://sms.example", "https://", "https://sms.example/path",
    "https://sms.example?token=x", "https://sms.example#fragment",
    "https://user:password@sms.example", "https://sms.example:invalid",
    "https://sms.example:99999", "https://sms.example:0", "https://sms .example",
])
def test_production_requires_valid_trusted_https_origin(origin):
    security = WebhookSecurity(TOKEN, origin, True)
    assert security.check("https://forged-host.example/sms", {}, None) is Verdict.MISCONFIGURED


def test_production_does_not_trust_request_host_when_origin_missing():
    url = "https://attacker.example/sms"
    signature = compute_signature(TOKEN, url, {})
    assert WebhookSecurity(TOKEN, None, True).check(url, {}, signature) is Verdict.MISCONFIGURED


def test_production_verifies_configured_origin_not_request_host():
    security = WebhookSecurity(TOKEN, "https://sms.example", True)
    params = {"Body": "HELP"}
    signature = compute_signature(TOKEN, "https://sms.example/sms", params)
    assert security.check("http://internal/sms", params, signature) is Verdict.ACCEPT
    forged = compute_signature(TOKEN, "https://attacker.example/sms", params)
    assert security.check("https://attacker.example/sms", params, forged) is Verdict.REJECT


@pytest.mark.parametrize("signature", ["invalid", "é", "☃", "", None])
def test_invalid_signature_is_rejected_without_exception(signature):
    assert not is_valid_signature(TOKEN, "https://sms.example/sms", {}, signature)


def test_malformed_request_port_is_rejected_without_exception():
    assert not is_valid_signature(TOKEN, "https://sms.example:bad/sms", {}, "abc")


def test_bad_origin_configuration_returns_503_without_consent_mutation(monkeypatch):
    import app.main as main
    monkeypatch.setenv("SHELTERLINK_ENV", "production")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    def forbidden():
        pytest.fail("consent backend must not be used when origin is misconfigured")
    monkeypatch.setattr(main, "get_opt_out_store", forbidden)
    data = {"Body": "START", "From": "+16125550100"}
    signature = compute_signature(TOKEN, "http://testserver/sms", data)
    response = client.post("/sms", data=data, headers={"X-Twilio-Signature": signature})
    assert response.status_code == 503
    assert "<Message>" not in response.text


def test_ipv6_default_port_variants_preserve_brackets():
    params = {"Body": "HELP"}
    signature = compute_signature(TOKEN, "https://[::1]:443/sms", params)
    assert is_valid_signature(TOKEN, "https://[::1]/sms", params, signature)
