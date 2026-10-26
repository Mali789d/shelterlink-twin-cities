"""Audit is a read-only review aid, not a provenance or deployment grant."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from app.audit_directory import audit_resources
from app.data import load_resources
from app.export_directory import directory_snapshot

AT = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def resource(identity="a", **changes):
    return load_resources()[0].model_copy(update={"id": identity, "is_sample": False,
                                                "verified_at": AT, **changes})


def test_all_blockers_reported_together_sorted_without_contact_data():
    data = [resource("z", is_sample=True, verified_at=AT + timedelta(seconds=1)),
            resource("b", verified_at=AT - timedelta(hours=24, seconds=1)),
            resource("a", is_sample=True)]
    report = audit_resources(data, AT)
    assert report["blockers"] == {"empty": False, "sample_ids": ["a", "z"],
                                  "stale_ids": ["b"], "future_ids": ["z"]}
    assert not report["export_validation_passes"]
    assert not report["provider_verification_confirmed"]
    assert "address" not in json.dumps(report)
    assert "phone" not in json.dumps(report)


@pytest.mark.parametrize("age,passes", [(0, True), (24 * 3600, True),
                                        (24 * 3600 + 1, False), (-1, False)])
def test_export_boundary_matches_real_exporter(age, passes):
    records = [resource(verified_at=AT - timedelta(seconds=age))]
    assert audit_resources(records, AT)["export_validation_passes"] is passes
    if passes:
        assert directory_snapshot(records, AT)["resources"]
    else:
        with pytest.raises(ValueError):
            directory_snapshot(records, AT)


def test_empty_is_blocked():
    assert audit_resources([], AT)["blockers"]["empty"]
    assert not audit_resources([], AT)["export_validation_passes"]


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        audit_resources([], AT.replace(tzinfo=None))


def test_duplicate_normalized_ids_and_bypassed_invalid_models_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        audit_resources([resource("a"), resource(" a ")], AT)
    with pytest.raises(ValueError):
        audit_resources([resource(latitude=91)], AT)


def test_timezone_offsets_compare_same_instants():
    other = AT.astimezone(timezone(timedelta(hours=-5)))
    assert audit_resources([resource(verified_at=other)], AT)["export_validation_passes"]


def test_audit_does_not_mutate_models():
    item = resource(is_sample=True)
    before = item.model_dump()
    audit_resources([item], AT)
    assert item.model_dump() == before


def test_cli_does_not_write_source_or_other_files(tmp_path):
    source = tmp_path / "resources.json"
    source.write_text(json.dumps([resource(is_sample=True).model_dump(mode="json")]))
    before = source.read_bytes()
    result = subprocess.run([sys.executable, "-m", "app.audit_directory", str(source)],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["blockers"]["sample_ids"] == ["a"]
    assert not report["provider_verification_confirmed"]
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]


def test_reachability_and_hours_warnings_sorted_ids_only():
    base = resource("full")
    data = [
        resource("z-walkin", phone=None, website=None),
        resource("b-nocontact-nohours", phone=None, website=None, hours={}),
        resource("a-nohours", hours={}),
        base,
    ]
    report = audit_resources(data, AT)
    assert report["warnings"] == {"walk_in_only_ids": ["b-nocontact-nohours", "z-walkin"],
                                  "no_hours_ids": ["a-nohours", "b-nocontact-nohours"]}
    # Warnings never gate export validation.
    assert report["export_validation_passes"]
    # Warning keys and values must not leak contact fields into the report.
    assert "address" not in json.dumps(report)
    assert "phone" not in json.dumps(report)
    assert "website" not in json.dumps(report)


def test_phone_or_website_alone_is_reachable_and_hours_present_is_no_warning():
    data = [resource("a", website=None),
            resource("b", phone=None, website="https://example.com/b"),
            resource("c", phone=None, website=None, hours={1: [("09:00", "17:00")]})]
    report = audit_resources(data, AT)
    assert report["warnings"] == {"walk_in_only_ids": ["c"], "no_hours_ids": []}


def test_empty_directory_has_no_warnings():
    report = audit_resources([], AT)
    assert report["warnings"] == {"walk_in_only_ids": [], "no_hours_ids": []}
    assert not report["export_validation_passes"]
