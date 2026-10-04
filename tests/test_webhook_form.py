from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.security import compute_signature
from app.webhook_form import MAX_BODY_BYTES, MAX_FIELDS

client = TestClient(main.app)


@pytest.fixture
def no_side_effects(monkeypatch):
    def forbidden():
        pytest.fail("Rejected input must not touch consent storage")
    monkeypatch.setattr(main, "get_opt_out_store", forbidden)


def post(content, content_type="application/x-www-form-urlencoded", headers=None):
    return client.post("/sms", content=content,
                       headers={"Content-Type": content_type, **(headers or {})})


@pytest.mark.parametrize("content_type", ["application/json", "multipart/form-data", "text/plain"])
def test_wrong_content_type_rejected(content_type, no_side_effects):
    assert post("Body=START&From=x", content_type).status_code == 415


def test_missing_content_type_rejected(no_side_effects):
    assert client.post("/sms", content=b"Body=START&From=x").status_code == 415


def test_oversized_body_rejected_without_content_length(no_side_effects):
    chunks = iter([b"Body=", b"x" * MAX_BODY_BYTES])
    assert post(chunks).status_code == 413


def test_field_limit_rejected(no_side_effects):
    assert post("&".join(f"x{i}=v" for i in range(MAX_FIELDS + 1))).status_code == 400


@pytest.mark.parametrize("content", [b"Body=\xff", "Body=%FF", "Body=%", "Body=%2G"])
def test_invalid_encoding_rejected(content, no_side_effects):
    assert post(content).status_code == 400


@pytest.mark.parametrize("field", ["Body", "From", "To", "MessageSid", "SmsSid", "AccountSid"])
def test_duplicate_critical_fields_rejected_even_when_signed(field, monkeypatch, no_side_effects):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://sms.example")
    values = {"Body": ["START"], "From": ["+16125550100"], field: ["a", "b"]}
    signature = compute_signature("test", "https://sms.example/sms", values)
    assert post(urlencode(values, doseq=True), headers={"X-Twilio-Signature": signature}).status_code == 400


def test_utf8_content_and_charset_work_with_signature(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://sms.example")
    values = {"Body": "55101 comida español", "From": "+16125550199"}
    signature = compute_signature("test", "https://sms.example/sms", values)
    response = post(urlencode(values), "application/x-www-form-urlencoded; charset=UTF-8",
                    {"X-Twilio-Signature": signature})
    assert response.status_code == 200
    assert "Recursos más cercanos" in response.text


def test_repeated_noncritical_fields_still_signed_as_all_values(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://sms.example")
    values = {"Body": ["HELP"], "From": ["+16125550199"], "Extra": ["b", "a"]}
    signature = compute_signature("test", "https://sms.example/sms", values)
    assert post(urlencode(values, doseq=True), headers={"X-Twilio-Signature": signature}).status_code == 200


def test_exact_body_limit_is_accepted_but_next_byte_is_not():
    prefix = "Body=HELP&From=%2B16125550199&Padding="
    content = prefix + "x" * (MAX_BODY_BYTES - len(prefix))
    assert post(content).status_code == 200
    assert post(content + "x").status_code == 413


def test_exact_field_limit_is_accepted():
    content = "Body=HELP&From=%2B16125550199&" + "&".join(
        f"x{i}=v" for i in range(MAX_FIELDS - 2)
    )
    assert post(content).status_code == 200
