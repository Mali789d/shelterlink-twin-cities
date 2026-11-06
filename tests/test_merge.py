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


@pytest.mark.parametrize("policy", ["reject", "replace", "keep"])
@pytest.mark.parametrize("side", ["base", "candidate"])
def test_direct_merge_rejects_duplicate_ids_within_either_input(policy, side):
    duplicate = validated(resource("duplicated"), resource("duplicated", "Different Site"))
    base = duplicate if side == "base" else validated(resource("base"))
    candidate = duplicate if side == "candidate" else validated(resource("candidate"))
    with pytest.raises(ValueError, match=f"{side} snapshot contains duplicate IDs"):
        merge_resources(base, candidate, on_conflict=policy)


@pytest.mark.parametrize("side", ["base", "candidate"])
@pytest.mark.parametrize("update", [
    {"latitude": float("nan")}, {"is_sample": "false"}, {"hours": {0: [("17:00", "09:00")]}},
])
def test_direct_merge_revalidates_models_that_bypassed_validation(side, update):
    original = validated(resource(side))[0]
    malformed = original.model_copy(update=update)
    base = [malformed] if side == "base" else []
    candidate = [malformed] if side == "candidate" else []
    with pytest.raises(ValueError):
        merge_resources(base, candidate)
    # The caller's original record was not modified while checking its copy.
    assert original.is_sample is True
    assert original.latitude == 44.98


def test_generator_inputs_are_consumed_once_and_preserve_all_records():
    base = (item for item in validated(resource("base")))
    candidate = (item for item in validated(resource("candidate")))
    result = merge_resources(base, candidate)
    assert [item.id for item in result["resources"]] == ["base", "candidate"]
    assert result["added"] == ["candidate"]
    assert all(item.is_sample is True for item in result["resources"])


def test_checked_merge_does_not_mutate_inputs():
    base = validated(resource("base"))
    candidate = validated(resource("candidate"))
    before = [item.model_dump() for item in base + candidate]
    merge_resources(base, candidate)
    assert [item.model_dump() for item in base + candidate] == before


def test_identical_candidate_under_replace_is_unchanged_not_replaced(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    candidate = write_snapshot(tmp_path / "candidate.json", resource())
    output = tmp_path / "merged.json"
    report = merge_files(base, candidate, output, on_conflict="replace")
    assert report["replaced"] == [] and report["unchanged"] == ["hc-101"]
    assert report["added"] == [] and report["skipped"] == []
    assert report["resource_count"] == 1
    # Nothing was applied: the merged content is exactly the base record.
    assert load_resources(output) == validated(resource())


def test_replace_separates_changed_from_unchanged_records(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource(), resource("hc-102", "Second Site"))
    candidate = write_snapshot(tmp_path / "candidate.json", resource(),
                               resource("hc-102", "Renamed Site"))
    output = tmp_path / "merged.json"
    report = merge_files(base, candidate, output, on_conflict="replace")
    assert report["replaced"] == ["hc-102"] and report["unchanged"] == ["hc-101"]
    names = {item.id: item.name for item in load_resources(output)}
    assert names == {"hc-101": "Hope Center", "hc-102": "Renamed Site"}


def test_unchanged_replacement_raises_no_phantom_duplicate_flag(tmp_path):
    # A pre-existing look-alike pair (same name, different IDs) is deliberately
    # left out of the report unless the merge actually touches one of them.
    base = write_snapshot(tmp_path / "base.json", resource(),
                          resource("hc-102", "Hope Center"))
    candidate = write_snapshot(tmp_path / "candidate.json", resource())
    output = tmp_path / "merged.json"
    report = merge_files(base, candidate, output, on_conflict="replace")
    assert report["unchanged"] == ["hc-101"] and report["possible_duplicates"] == []


def test_changed_replacement_still_flags_look_alikes_it_touches(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource(),
                          resource("hc-102", "Hope Center"))
    candidate = write_snapshot(tmp_path / "candidate.json",
                               resource(name="Hope Center", phone="6125550100"))
    output = tmp_path / "merged.json"
    report = merge_files(base, candidate, output, on_conflict="replace")
    assert report["replaced"] == ["hc-101"]
    assert report["possible_duplicates"] == [
        {"ids": ["hc-101", "hc-102"], "rules": ["same_name", "same_location"]}]


def test_keep_policy_reports_identical_candidates_as_skipped(tmp_path):
    base = write_snapshot(tmp_path / "base.json", resource())
    candidate = write_snapshot(tmp_path / "candidate.json", resource())
    output = tmp_path / "merged.json"
    report = merge_files(base, candidate, output, on_conflict="keep")
    assert report["skipped"] == ["hc-101"] and report["unchanged"] == []
    assert load_resources(output) == validated(resource())


def test_merge_resources_report_carries_the_unchanged_key():
    report = merge_resources(validated(resource()), validated(resource("hc-102", "Site")),
                             on_conflict="reject")
    assert report["unchanged"] == []
