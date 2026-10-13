"""Invalid offline inputs must not produce a misleading readiness pass."""
from datetime import datetime, timezone

import pytest

from app.data import load_resources
from app.readiness import readiness_checks

AT = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


class OfflineGeocoder:
    def geocode(self, location):
        raise AssertionError("readiness must not make geocoder requests")


def item(**changes):
    return load_resources()[0].model_copy(update={"is_sample": False, "verified_at": AT, **changes})


@pytest.mark.parametrize("changes", [{"latitude": 91}, {"source_url": "https://u:p@example.com"},
                                     {"verified_at": AT.replace(tzinfo=None)}, {"id": " "}])
def test_bypassed_model_validation_fails_closed(changes):
    checks = readiness_checks([item(**changes)], OfflineGeocoder(), {}, AT)
    assert checks["verified_resource_snapshot"] is False
    assert checks["current_resource_snapshot"] is False


def test_normalized_duplicate_ids_fail_closed():
    checks = readiness_checks([item(id="a"), item(id=" a ")], OfflineGeocoder(), {}, AT)
    assert not checks["verified_resource_snapshot"]
    assert not checks["current_resource_snapshot"]


@pytest.mark.parametrize("geocoder", [None, object(), type("Bad", (), {"geocode": 123})()])
def test_missing_callable_geocoder_cannot_pass(geocoder):
    assert not readiness_checks([item()], geocoder, {}, AT)["production_geocoder"]


def test_valid_geocoder_interface_is_checked_without_calling_it():
    checks = readiness_checks([item()], OfflineGeocoder(), {}, AT)
    assert checks["production_geocoder"]
    assert checks["verified_resource_snapshot"] and checks["current_resource_snapshot"]


def test_naive_review_clock_fails_closed():
    assert not readiness_checks([item()], OfflineGeocoder(), {}, AT.replace(tzinfo=None))[
        "current_resource_snapshot"]


def test_invalid_resource_objects_return_boolean_checks_not_private_exception_text():
    checks = readiness_checks([None], OfflineGeocoder(), {}, AT)
    assert all(isinstance(value, bool) for value in checks.values())
    assert not checks["verified_resource_snapshot"]
