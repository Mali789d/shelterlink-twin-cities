"""Synthetic snapshot change reports do not establish live provider data."""
import json
import subprocess
import sys
from datetime import timedelta

import pytest

from app.data import load_resources
from app.review_changes import compare_resources


def item(identity="fixture"):
    return load_resources()[0].model_copy(update={"id": identity})


def test_reports_added_removed_changed_and_unchanged_in_stable_order():
    old = [item("removed"), item("same"), item("updated")]
    new = [item("new-z"), item("updated").model_copy(update={"name": "Changed fixture"}),
           item("same"), item("new-a")]
    report = compare_resources(old, new)
    assert report["added"] == ["new-a", "new-z"]
    assert report["removed"] == ["removed"]
    assert report["changed"] == [{"id": "updated", "fields": ["name"]}]
    assert report["unchanged_count"] == 1
    assert "Not provider verification" in report["notice"]
    assert compare_resources(reversed(old), reversed(new)) == report


@pytest.mark.parametrize("field,value", [
    ("name", "Changed fixture"), ("address", "Changed address"),
    ("latitude", 1), ("source_url", "https://example.com/new"),
    ("is_sample", False), ("availability", "full"),
    ("hours", {0: [("08:00", "09:00")]}),
])
def test_material_changes_are_explicit(field, value):
    resource = item()
    report = compare_resources([resource], [resource.model_copy(update={field: value})])
    assert report["changed"] == [{"id": resource.id, "fields": [field]}]


def test_timestamp_only_refresh_is_visible_not_silently_unchanged():
    resource = item()
    report = compare_resources([resource], [resource.model_copy(update={
        "verified_at": resource.verified_at + timedelta(seconds=1)})])
    assert report["changed"][0]["fields"] == ["verified_at"]


@pytest.mark.parametrize("side", ["before", "after"])
def test_duplicate_or_invalid_input_rejects_the_entire_review(side):
    resource = item()
    for bad in [[resource, resource], [resource.model_copy(update={"latitude": 91})]]:
        args = (bad, [resource]) if side == "before" else ([resource], bad)
        with pytest.raises(ValueError):
            compare_resources(*args)


def test_empty_and_identical_snapshots_are_valid_reviews():
    assert compare_resources([], [item()])["added"] == ["fixture"]
    assert compare_resources([item()], [item()])["unchanged_count"] == 1
    assert compare_resources([], [])["changed"] == []


def test_cli_is_read_only_and_emits_no_raw_contact_values(tmp_path):
    first, second = tmp_path / "old.json", tmp_path / "new.json"
    resource = item()
    first.write_text(json.dumps([resource.model_dump(mode="json")]))
    second.write_text(json.dumps([resource.model_copy(update={"phone": "555-0100"}).model_dump(mode="json")]))
    before = (first.read_bytes(), second.read_bytes())
    result = subprocess.run([sys.executable, "-m", "app.review_changes", str(first), str(second)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["changed"] == [{"id": "fixture", "fields": ["phone"]}]
    assert "555-0100" not in result.stdout
    assert (first.read_bytes(), second.read_bytes()) == before


def test_lost_contact_fields_and_hours_flagged_without_values():
    resource = item().model_copy(update={"website": "https://example.org/fixture"})
    stripped = resource.model_copy(update={"phone": None, "website": None, "hours": {}})
    report = compare_resources([resource], [stripped])
    assert report["regressions"] == [{
        "id": "fixture", "lost_fields": ["hours", "phone", "website"],
        "returned_to_sample": False, "verification_moved_backwards": False}]
    dump = json.dumps(report)
    assert resource.phone not in dump
    assert str(resource.website) not in dump


def test_gaining_fields_is_a_change_not_a_regression():
    resource = item().model_copy(update={"phone": None, "hours": {}})
    enriched = resource.model_copy(update={"phone": "555-0100",
                                           "hours": {0: [("08:00", "17:00")]}})
    report = compare_resources([resource], [enriched])
    assert report["changed"] == [{"id": "fixture", "fields": ["hours", "phone"]}]
    assert report["regressions"] == []


def test_verification_moving_backwards_is_flagged_across_timezone_offsets():
    resource = item().model_copy(update={"verified_at": "2026-10-20T12:00:00+00:00"})
    older = resource.model_copy(update={"verified_at": "2026-10-20T06:59:59-05:00"})
    report = compare_resources([resource], [older])
    assert report["regressions"] == [{
        "id": "fixture", "lost_fields": [],
        "returned_to_sample": False, "verification_moved_backwards": True}]
    # The same instant written with a different offset is not a regression.
    same = resource.model_copy(update={"verified_at": "2026-10-20T07:00:00-05:00"})
    assert compare_resources([resource], [same])["regressions"] == []


def test_returned_to_sample_flagged_and_verified_stays_quiet():
    verified = item().model_copy(update={"is_sample": False})
    resampled = verified.model_copy(update={"is_sample": True})
    report = compare_resources([verified], [resampled])
    assert report["regressions"] == [{
        "id": "fixture", "lost_fields": [],
        "returned_to_sample": True, "verification_moved_backwards": False}]
    # A record leaving sample status is progress, never a regression.
    assert compare_resources([resampled], [verified])["regressions"] == []


def test_added_and_removed_records_produce_no_regressions():
    report = compare_resources([item("gone")], [item("new")])
    assert report["regressions"] == []
    assert compare_resources([], [])["regressions"] == []


@pytest.mark.parametrize("field,value", [
    ("name", "New provider name"), ("address", "New site address"),
    ("latitude", 44.99), ("longitude", -93.30), ("phone", "555-0199"),
    ("website", "https://example.org/new"), ("category", "shower"),
    ("hours", {0: [("08:00", "09:00")]}), ("availability", "full"),
    ("source_name", "New provider"), ("source_url", "https://example.org/source"),
])
def test_changed_facts_cannot_quietly_inherit_an_old_verification(field, value):
    resource = item()
    report = compare_resources([resource], [resource.model_copy(update={field: value})])
    assert report["verification_reviews"] == [{
        "id": "fixture", "fields": [field], "promoted_from_sample": False}]
    assert str(value) not in json.dumps(report)


def test_sample_promotion_needs_a_fresh_check_even_without_changed_facts():
    resource = item()
    promoted = resource.model_copy(update={"is_sample": False})
    assert compare_resources([resource], [promoted])["verification_reviews"] == [{
        "id": "fixture", "fields": [], "promoted_from_sample": True}]


def test_equal_instant_different_offset_does_not_hide_review():
    resource = item().model_copy(update={"verified_at": "2026-11-04T12:00:00+00:00"})
    changed = resource.model_copy(update={"phone": "555-0199",
                                          "verified_at": "2026-11-04T06:00:00-06:00"})
    assert compare_resources([resource], [changed])["verification_reviews"][0]["fields"] == ["phone"]


def test_newer_date_is_not_a_missing_reverification_warning():
    resource = item()
    changed = resource.model_copy(update={"phone": "555-0199",
        "verified_at": resource.verified_at + timedelta(seconds=1)})
    report = compare_resources([resource], [changed])
    assert report["verification_reviews"] == []
    assert "Not provider verification" in report["notice"]


def test_backwards_date_with_changed_facts_has_both_warnings():
    resource = item()
    changed = resource.model_copy(update={"phone": None,
        "verified_at": resource.verified_at - timedelta(seconds=1)})
    report = compare_resources([resource], [changed])
    assert report["verification_reviews"][0]["fields"] == ["phone"]
    assert report["regressions"][0]["verification_moved_backwards"] is True


def test_reviews_are_sorted_and_do_not_expose_changed_values():
    resources = [item("z"), item("a")]
    changed = [r.model_copy(update={"phone": "555-0199", "address": "Private changed address",
                                   "is_sample": False}) for r in resources]
    report = compare_resources(resources, changed)
    assert report["verification_reviews"] == [
        {"id": rid, "fields": ["address", "phone"], "promoted_from_sample": True}
        for rid in ["a", "z"]]
    assert compare_resources(reversed(resources), reversed(changed)) == report
    assert "555-0199" not in json.dumps(report)
    assert "Private changed address" not in json.dumps(report)


def test_timestamp_only_and_unchanged_and_added_removed_do_not_warn():
    resource = item()
    later = resource.model_copy(update={"verified_at": resource.verified_at + timedelta(hours=1)})
    for before, after in [([resource], [later]), ([resource], [resource]),
                          ([], [resource]), ([resource], []), ([], [])]:
        assert compare_resources(before, after)["verification_reviews"] == []
