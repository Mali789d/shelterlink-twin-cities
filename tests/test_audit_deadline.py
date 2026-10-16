"""Reviewers need to know when a currently valid snapshot stops being fresh."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.audit_directory import audit_resources
from app.data import load_resources

AT = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


def item(identity, verified, sample=False):
    return load_resources()[0].model_copy(update={"id": identity, "is_sample": sample,
                                                "verified_at": verified})


def test_oldest_record_sets_deadline_independent_of_input_order():
    newer = item("newer", AT - timedelta(hours=1))
    older = item("older", AT - timedelta(hours=23))
    for records in ([newer, older], [older, newer]):
        report = audit_resources(records, AT)
        assert report["freshness_deadline"] == (AT + timedelta(hours=1)).isoformat()
        assert report["freshness_seconds_remaining"] == 3600
        assert not report["provider_verification_confirmed"]


def test_inclusive_boundary_reports_zero_seconds_not_a_new_day():
    report = audit_resources([item("a", AT - timedelta(hours=24))], AT)
    assert report["export_validation_passes"]
    assert report["freshness_seconds_remaining"] == 0


@pytest.mark.parametrize("records", [[], [item("sample", AT, True)],
    [item("stale", AT - timedelta(hours=25))], [item("future", AT + timedelta(seconds=1))]])
def test_blocked_snapshot_has_no_misleading_freshness_deadline(records):
    report = audit_resources(records, AT)
    assert report["freshness_deadline"] is None
    assert report["freshness_seconds_remaining"] is None


def test_deadline_uses_elapsed_time_across_fall_back():
    zone = ZoneInfo("America/Chicago")
    verified = datetime(2026, 10, 31, 12, tzinfo=zone)
    at = datetime(2026, 11, 1, 10, tzinfo=zone)
    report = audit_resources([item("a", verified)], at)
    assert report["freshness_deadline"] == "2026-11-01T17:00:00+00:00"
    assert report["freshness_seconds_remaining"] == 3600
