"""Pasted whitespace must not silently disable production safeguards.

Environment dashboards routinely add surrounding whitespace to pasted values.
SHELTERLINK_ENV="production " used to evaluate as development: unsigned webhook
traffic accepted, in-memory opt-outs, sample data served. A whitespace-only
TWILIO_AUTH_TOKEN used to look configured, and a whitespace PUBLIC_BASE_URL was
not treated as unset. Configuration is normalized before evaluation.
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app.main as main
from app.readiness import readiness_checks
from app.security import Verdict, WebhookSecurity


def post_sms():
    return TestClient(main.app).post(
        "/sms", data={"Body": "55415 shelter", "From": "+15555550100"})


def test_production_env_with_surrounding_whitespace_still_fails_closed(monkeypatch):
    monkeypatch.setenv("SHELTERLINK_ENV", " Production\n")
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    response = post_sms()
    assert response.status_code == 503
    assert response.text == "SMS webhook is not configured"


def test_whitespace_token_is_not_a_configured_token(monkeypatch):
    monkeypatch.setenv("SHELTERLINK_ENV", "production ")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "   ")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    # No usable token in production fails closed as misconfigured, not as 403s.
    assert post_sms().status_code == 503


def test_whitespace_token_in_development_means_unsigned(monkeypatch):
    monkeypatch.setenv("SHELTERLINK_ENV", "development")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", " \t ")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    # Development without a real token keeps accepting unsigned local traffic.
    assert post_sms().status_code == 200


def test_whitespace_public_origin_is_treated_as_unset():
    security = WebhookSecurity.from_env({
        "PUBLIC_BASE_URL": "   ",
        "TWILIO_AUTH_TOKEN": "token",
        "SHELTERLINK_ENV": "production",
    })
    assert security.public_base_url is None
    # A missing public origin in production is misconfigured, never signed against.
    assert security.check("https://internal.example/sms", {}, "sig") is Verdict.MISCONFIGURED


def test_origin_and_token_keep_valid_inner_content():
    security = WebhookSecurity.from_env({
        "PUBLIC_BASE_URL": "  https://example.com/  ",
        "TWILIO_AUTH_TOKEN": " real-token ",
        "SHELTERLINK_ENV": " production ",
    })
    assert security.public_base_url == "https://example.com"
    assert security.auth_token == "real-token"
    assert security.production is True


def test_readiness_reports_whitespace_padded_production_mode():
    checks = readiness_checks([], None, {"SHELTERLINK_ENV": "Production "},
                              datetime.now(timezone.utc))
    assert checks["production_mode"] is True
