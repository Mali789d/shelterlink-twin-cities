"""Possible-duplicate flags are deterministic, report-only, and ID-only."""
import json
import subprocess
import sys

from app.duplicates import find_possible_duplicates, normalized_name, normalized_phone
from app.models import Resource


def resource(resource_id, name="Hope Center", phone=None, latitude=44.98, longitude=-93.27):
    record = {
        "id": resource_id, "name": name, "category": "shelter",
        "address": "100 Example Ave, Minneapolis", "latitude": latitude,
        "longitude": longitude, "source_name": "Hennepin County",
        "source_url": "https://example.org/hc", "verified_at": "2026-10-20T12:00:00-05:00",
        "is_sample": True,
    }
    if phone is not None:
        record["phone"] = phone
    return Resource.model_validate(record)


def test_same_phone_in_different_formats_is_flagged():
    left = resource("a", "Alpha Shelter", phone="(612) 555-0100")
    right = resource("b", "Bravo Shelter", phone="+1 612-555-0100",
                     latitude=44.95, longitude=-93.09)
    report = find_possible_duplicates([left, right])
    assert report["flags"] == [{"ids": ["a", "b"], "rules": ["same_phone"]}]


def test_extension_and_country_code_do_not_hide_a_match():
    assert normalized_phone("612-555-0100 x12") == normalized_phone("+1 (612) 555-0100")


def test_same_name_with_punctuation_drift_is_flagged():
    left = resource("a", "Hope Center")
    right = resource("b", "hope  center!", latitude=44.95, longitude=-93.09)
    assert find_possible_duplicates([left, right])["flags"][0]["rules"] == ["same_name"]


def test_same_building_coordinates_are_flagged():
    left = resource("a", "Alpha Shelter", latitude=44.98000, longitude=-93.27000)
    right = resource("b", "Bravo Shelter", latitude=44.98010, longitude=-93.27005)
    assert find_possible_duplicates([left, right])["flags"][0]["rules"] == ["same_location"]


def test_clearly_separate_records_raise_no_flags():
    left = resource("a", "Alpha Shelter", phone="612-555-0100")
    right = resource("b", "Bravo Meals", phone="651-555-0199",
                     latitude=44.95, longitude=-93.09)
    report = find_possible_duplicates([left, right])
    assert report["flag_count"] == 0 and report["flags"] == []


def test_missing_phones_never_match_each_other():
    left = resource("a", "Alpha Shelter")
    right = resource("b", "Bravo Shelter", latitude=44.95, longitude=-93.09)
    assert find_possible_duplicates([left, right])["flags"] == []


def test_one_pair_can_carry_several_rules():
    left = resource("a", "Hope Center", phone="612-555-0100")
    right = resource("b", "Hope Center", phone="6125550100")
    assert find_possible_duplicates([left, right])["flags"][0]["rules"] == [
        "same_phone", "same_name", "same_location"]


def test_output_names_ids_and_rules_only_never_contact_details():
    left = resource("a", "Alpha Shelter", phone="612-555-0100")
    right = resource("b", "Alpha Shelter", phone="6125550100")
    rendered = json.dumps(find_possible_duplicates([left, right]))
    assert "612" not in rendered and "Example Ave" not in rendered
    assert "Alpha" not in rendered


def test_flags_are_sorted_deterministically_regardless_of_input_order():
    records = [resource("c", "Charlie"), resource("a", "Alpha"), resource("b", "Alpha")]
    first = find_possible_duplicates(records)
    second = find_possible_duplicates(list(reversed(records)))
    assert first == second
    assert first["flags"][0]["ids"] == ["a", "b"]


def test_empty_snapshot_reports_zero_flags():
    report = find_possible_duplicates([])
    assert report["resource_count"] == 0 and report["flag_count"] == 0


def test_cli_round_trip(tmp_path):
    snapshot = tmp_path / "resources.json"
    snapshot.write_text(json.dumps([resource("a", "Alpha", phone="612-555-0100").model_dump(mode="json"),
                                    resource("b", "Beta", phone="6125550100",
                                             latitude=44.95, longitude=-93.09).model_dump(mode="json")]),
                        encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "app.duplicates", str(snapshot)],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["flags"] == [{"ids": ["a", "b"], "rules": ["same_phone"]}]
    assert "Not merge approval" in report["notice"]


def test_name_normalization_keeps_distinct_names_distinct():
    assert normalized_name("Hope Center") != normalized_name("Hope Center North")


def test_same_website_with_formatting_drift_is_flagged():
    left = resource("a", "Alpha Shelter").model_copy(
        update={"website": "https://www.example.org/hope/?utm_source=export#top"})
    right = resource("b", "Bravo Shelter", latitude=44.95, longitude=-93.09).model_copy(
        update={"website": "http://example.org/hope"})
    report = find_possible_duplicates([left, right])
    assert report["flags"] == [{"ids": ["a", "b"], "rules": ["same_website"]}]


def test_distinct_program_pages_on_one_org_site_do_not_flag():
    left = resource("a", "Alpha Shelter").model_copy(
        update={"website": "https://example.org/alpha"})
    right = resource("b", "Bravo Shelter", latitude=44.95, longitude=-93.09).model_copy(
        update={"website": "https://example.org/bravo"})
    assert find_possible_duplicates([left, right])["flags"] == []


def test_missing_website_never_flags():
    left = resource("a", "Alpha Shelter")
    right = resource("b", "Bravo Shelter", latitude=44.95, longitude=-93.09)
    assert find_possible_duplicates([left, right])["flags"] == []


def test_website_rule_combines_with_other_rules_in_order():
    left = resource("a", "Hope Center", phone="612-555-0100").model_copy(
        update={"website": "https://example.org/hope"})
    right = resource("b", "hope center", phone="(612) 555-0100").model_copy(
        update={"website": "https://example.org/hope/"})
    rules = find_possible_duplicates([left, right])["flags"][0]["rules"]
    # Same default coordinates mean same_location fires too, listed last.
    assert rules == ["same_phone", "same_name", "same_website", "same_location"]
