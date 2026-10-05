from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.data import load_resources
from app.geocoding import DevelopmentGeocoder
from app.readiness import readiness_checks
from test_lambda import event
from app.lambda_handler import handler

NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
ENV = {
    "SHELTERLINK_ENV": "production", "TWILIO_AUTH_TOKEN": "private-token",
    "PUBLIC_BASE_URL": "https://sms.example", "OPT_OUT_TABLE": "private-table",
    "OPT_OUT_HASH_SALT": "private-salt-with-at-least-32-characters",
}


class TestGeocoder:
    def geocode(self, location):
        return None


def valid_resources():
    return [load_resources()[0].model_copy(update={"is_sample": False, "verified_at": NOW})]


def test_all_offline_checks_can_pass_without_asserting_external_verification():
    assert all(readiness_checks(valid_resources(), TestGeocoder(), ENV, NOW).values())


@pytest.mark.parametrize("age", [timedelta(hours=25), timedelta(minutes=-1)])
def test_stale_and_future_data_not_ready(age):
    resources = valid_resources()
    resources[0] = resources[0].model_copy(update={"verified_at": NOW - age})
    assert not readiness_checks(resources, TestGeocoder(), ENV, NOW)["current_resource_snapshot"]


def test_sample_and_empty_data_not_ready():
    for resources in (load_resources(), []):
        assert not readiness_checks(resources, TestGeocoder(), ENV, NOW)["verified_resource_snapshot"]


@pytest.mark.parametrize("key,check", [
    ("SHELTERLINK_ENV", "production_mode"), ("TWILIO_AUTH_TOKEN", "twilio_token_configured"),
    ("PUBLIC_BASE_URL", "public_https_origin"), ("OPT_OUT_TABLE", "durable_consent_configured"),
    ("OPT_OUT_HASH_SALT", "durable_consent_configured"),
])
def test_missing_config_reported_without_secret_values(key, check):
    env = {k: v for k, v in ENV.items() if k != key}
    assert not readiness_checks(valid_resources(), TestGeocoder(), env, NOW)[check]


def test_development_geocoder_blocks_readiness():
    assert not readiness_checks(valid_resources(), DevelopmentGeocoder(), ENV, NOW)["production_geocoder"]


def test_health_is_not_a_launch_ready_signal(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    client = TestClient(main.app)
    assert client.get("/health").status_code == 200
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["external_dependencies_verified"] is False
    for value in ("private-token", "private-table", ENV["OPT_OUT_HASH_SALT"]):
        assert value not in response.text


def test_ready_route_works_in_packaged_lambda():
    result = handler(event("/ready"), None)
    assert result["statusCode"] == 503
    assert "not_ready" in result["body"]
    assert "Path: /ready, Method: GET" in open("template.yaml").read()


def test_ready_endpoint_returns_configuration_only_success(monkeypatch):
    monkeypatch.setattr(main, "readiness_checks", lambda *args: {"offline_test": True})
    response = TestClient(main.app).get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "configuration_ready"
    assert response.json()["external_dependencies_verified"] is False
