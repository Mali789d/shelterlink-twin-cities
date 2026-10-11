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
