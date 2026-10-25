"""Merging applies reviewed candidates loudly: conflicts never pass silently."""
import json
import subprocess
import sys

import pytest

from app.data import load_resources
from app.merge import merge_files, merge_resources
from app.models import Resource


def resource(resource_id="hc-101", name="Hope Center", **overrides):
    record = {
        "id": resource_id, "name": name, "category": "shelter",
        "address": "100 Example Ave, Minneapolis", "latitude": 44.98, "longitude": -93.27,
        "source_name": "Hennepin County", "source_url": "https://example.org/hc",
        "verified_at": "2026-10-20T12:00:00-05:00", "is_sample": True,
    }
    record.update(overrides)
    return record


def write_snapshot(path, *resources):
    path.write_text(json.dumps(list(resources)), encoding="utf-8")
    return path


def validated(*records):
    return [Resource.model_validate(record) for record in records]


def test_disjoint_candidate_appends_and_reports_new_ids(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    candidate = write_snapshot(tmp_path / "candidate.json", resource("hc-102", "Second Site"))
    output = tmp_path / "merged.json"
    report = merge_files(base, candidate, output)
    assert report["added"] == ["hc-102"] and report["replaced"] == [] and report["skipped"] == []
    assert report["resource_count"] == 2
    assert "Not provider verification" in report["notice"]
    assert [item.id for item in load_resources(output)] == ["hc-101", "hc-102"]


def test_conflicting_ids_reject_by_default_without_touching_output(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    candidate = write_snapshot(tmp_path / "candidate.json", resource(name="Renamed Center"))
    output = tmp_path / "merged.json"
    with pytest.raises(ValueError, match="hc-101"):
        merge_files(base, candidate, output)
    assert not output.exists()


def test_replace_lists_every_applied_update(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource(), resource("hc-102", "Second Site"))
    candidate = write_snapshot(tmp_path / "candidate.json", resource(name="Renamed Center"))
    output = tmp_path / "merged.json"
    report = merge_files(base, candidate, output, on_conflict="replace")
    assert report["replaced"] == ["hc-101"] and report["added"] == []
    names = {item.id: item.name for item in load_resources(output)}
    assert names == {"hc-101": "Renamed Center", "hc-102": "Second Site"}


def test_keep_retains_base_records_and_reports_skips(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    candidate = write_snapshot(tmp_path / "candidate.json",
                               resource(name="Renamed Center"), resource("hc-102", "Second Site"))
    output = tmp_path / "merged.json"
    report = merge_files(base, candidate, output, on_conflict="keep")
    assert report["skipped"] == ["hc-101"] and report["added"] == ["hc-102"]
    names = {item.id: item.name for item in load_resources(output)}
    assert names == {"hc-101": "Hope Center", "hc-102": "Second Site"}


def test_unknown_policy_fails_loudly():
    with pytest.raises(ValueError, match="conflict policy"):
        merge_resources(validated(resource()), validated(resource()), on_conflict="yolo")


def test_merging_preserves_each_records_provenance_flag(tmp_path):
    reviewed = resource(is_sample=False)
    base = write_snapshot(tmp_path / "base.json", reviewed)
    candidate = write_snapshot(tmp_path / "candidate.json", resource("hc-102", "Second Site"))
    output = tmp_path / "merged.json"
    merge_files(base, candidate, output)
    flags = {item.id: item.is_sample for item in load_resources(output)}
    # A merge moves records; it never upgrades or downgrades provenance.
    assert flags == {"hc-101": False, "hc-102": True}


def test_output_never_replaces_an_input(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    candidate = write_snapshot(tmp_path / "candidate.json", resource("hc-102", "Second Site"))
    with pytest.raises(ValueError, match="must not replace"):
        merge_files(base, candidate, base)
    with pytest.raises(ValueError, match="must not replace"):
        merge_files(base, candidate, candidate)


def test_invalid_candidate_rejects_before_write(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([resource(latitude=999)]), encoding="utf-8")
    output = tmp_path / "merged.json"
    with pytest.raises(ValueError):
        merge_files(base, bad, output)
    assert not output.exists()


def test_within_candidate_duplicate_ids_fail_loudly(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    duplicate = tmp_path / "dup.json"
    duplicate.write_text(json.dumps([resource("hc-102"), resource("hc-102", "Copy")]),
                         encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate IDs"):
        merge_files(base, duplicate, tmp_path / "merged.json")


def test_cli_merge_round_trip(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    candidate = write_snapshot(tmp_path / "candidate.json", resource("hc-102", "Second Site"))
    output = tmp_path / "merged.json"
    result = subprocess.run(
        [sys.executable, "-m", "app.merge", str(base), str(candidate), str(output)],
        capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["added"] == ["hc-102"] and report["resource_count"] == 2
    assert output.exists()


def test_merge_flags_look_alikes_introduced_by_the_candidate(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource(phone="(612) 555-0100"))
    candidate = write_snapshot(tmp_path / "candidate.json",
                               resource("hc-102", "Second Site", phone="6125550100",
                                        latitude=45.05, longitude=-93.30))
    report = merge_files(base, candidate, tmp_path / "merged.json")
    assert report["possible_duplicates"] == [
        {"ids": ["hc-101", "hc-102"], "rules": ["same_phone"]}]


def test_merge_flags_introduced_name_and_location_look_alikes(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    drifted = resource("hc-103", "Hope  Center", latitude=44.98001, longitude=-93.27001)
    candidate = write_snapshot(tmp_path / "candidate.json", drifted)
    report = merge_files(base, candidate, tmp_path / "merged.json")
    flags = report["possible_duplicates"]
    assert [flag["ids"] for flag in flags] == [["hc-101", "hc-103"]]
    assert "same_name" in flags[0]["rules"] and "same_location" in flags[0]["rules"]


def test_merge_leaves_pre_existing_look_alike_pairs_out_of_the_report(tmp_path):
    twin = resource("hc-102", "Hope Center Twin")
    base = write_snapshot(tmp_path / "base.json", resource(), twin)
    candidate = write_snapshot(tmp_path / "candidate.json",
                               resource("hc-103", "Unrelated Site",
                                        latitude=45.05, longitude=-93.30))
    report = merge_files(base, candidate, tmp_path / "merged.json")
    assert report["possible_duplicates"] == []


def test_merge_without_look_alikes_reports_no_duplicates(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    candidate = write_snapshot(tmp_path / "candidate.json",
                               resource("hc-102", "Second Site",
                                        latitude=45.05, longitude=-93.30))
    report = merge_files(base, candidate, tmp_path / "merged.json")
    assert report["possible_duplicates"] == []


def test_replaced_records_participate_in_duplicate_checks(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource(),
                          resource("hc-102", "Meal Site", category="meal",
                                   address="200 Example Ave, Minneapolis",
                                   latitude=45.01, longitude=-93.29))
    renamed = resource("hc-102", "Hope Center", category="meal",
                       address="200 Example Ave, Minneapolis",
                       latitude=45.01, longitude=-93.29)
    candidate = write_snapshot(tmp_path / "candidate.json", renamed)
    report = merge_files(base, candidate, tmp_path / "merged.json",
                         on_conflict="replace")
    assert report["replaced"] == ["hc-102"]
    assert report["possible_duplicates"] == [
        {"ids": ["hc-101", "hc-102"], "rules": ["same_name"]}]


def test_merge_reports_no_contact_details_in_duplicate_flags(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource(phone="(612) 555-0100"))
    candidate = write_snapshot(tmp_path / "candidate.json",
                               resource("hc-102", "Second Site", phone="6125550100"))
    report = merge_files(base, candidate, tmp_path / "merged.json")
    assert "5550100" not in json.dumps(report["possible_duplicates"])
