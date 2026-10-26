"""Provider-export ingestion validates per record and never auto-promotes."""
import json
import subprocess
import sys

import pytest

from app.data import load_resources
from app.ingest import (ingest_records, load_mapping, read_provider_records,
                        write_candidate)
from app.models import Availability

MAPPING = {
    "id": "ProviderID", "name": "SiteName", "category": "ServiceType",
    "address": "StreetAddress", "latitude": "Lat", "longitude": "Lng",
    "source_name": "Publisher", "source_url": "PublisherURL", "verified_at": "CheckedOn",
}


def provider_record(**overrides):
    record = {
        "ProviderID": "hc-101", "SiteName": "Hope Center", "ServiceType": "shelter",
        "StreetAddress": "100 Example Ave, Minneapolis", "Lat": 44.98, "Lng": -93.27,
        "Publisher": "Hennepin County", "PublisherURL": "https://example.org/hc-101",
        "CheckedOn": "2026-10-20T12:00:00-05:00", "BedsTotal": 40, "Notes": "call ahead",
    }
    record.update(overrides)
    return record


def test_happy_path_applies_safe_defaults_and_ignores_extra_provider_fields():
    report = ingest_records([provider_record()], MAPPING)
    assert not report["rejections"]
    (resource,) = report["candidates"]
    assert resource.id == "hc-101"
    # Extra provider columns are ignored, and nothing is promoted automatically.
    assert resource.is_sample is True
    assert resource.availability is Availability.UNKNOWN


def test_dirty_row_rejects_itself_with_reasons_and_keeps_the_batch():
    good = provider_record()
    bad = provider_record(ProviderID="hc-102", Lat="north")
    report = ingest_records([good, bad], MAPPING)
    assert [item.id for item in report["candidates"]] == ["hc-101"]
    (rejection,) = report["rejections"]
    assert rejection["index"] == 1 and rejection["record_id"] == "hc-102"
    assert any("latitude" in message for message in rejection["errors"])
    assert "north" not in json.dumps(rejection)


def test_later_duplicate_id_rejects_instead_of_replacing():
    first = provider_record()
    duplicate = provider_record(SiteName="Other Site")
    report = ingest_records([first, duplicate], MAPPING)
    assert [item.id for item in report["candidates"]] == ["hc-101"]
    assert report["rejections"][0]["errors"] == ["duplicate resource ID"]


def test_non_dict_record_rejects_without_values():
    report = ingest_records([provider_record(), "not a record"], MAPPING)
    assert len(report["candidates"]) == 1
    assert report["rejections"][0]["errors"] == ["record must be a JSON object"]


def test_mapping_typo_fails_loudly(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps({**MAPPING, "addres": "StreetAddress"}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown resource fields: addres"):
        load_mapping(path)


def test_non_sample_promotion_requires_an_explicit_boolean():
    # A provider string like "false" must not silently flip the provenance flag.
    report = ingest_records([provider_record(is_sample="false")], {**MAPPING, "is_sample": "is_sample"})
    assert not report["candidates"]
    assert report["rejections"]
    explicit = provider_record(is_sample=False)
    report = ingest_records([explicit], {**MAPPING, "is_sample": "is_sample"})
    assert report["candidates"][0].is_sample is False


def test_candidate_round_trips_through_the_snapshot_loader(tmp_path):
    output = tmp_path / "candidate.json"
    report = ingest_records([provider_record()], MAPPING)
    write_candidate(report["candidates"], output, [])
    (loaded,) = load_resources(output)
    assert loaded.id == "hc-101" and loaded.is_sample is True


def test_candidate_output_never_replaces_an_input(tmp_path):
    source = tmp_path / "raw.json"
    source.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must not replace an input file"):
        write_candidate([], source, [source])


def test_cli_reports_candidates_and_rejections(tmp_path):
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps([provider_record(), provider_record(ProviderID="hc-102", Lng=None)]),
                   encoding="utf-8")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps(MAPPING), encoding="utf-8")
    output = tmp_path / "candidate.json"
    result = subprocess.run(
        [sys.executable, "-m", "app.ingest", str(raw), str(mapping), str(output)],
        capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["candidate_count"] == 1 and report["rejection_count"] == 1
    assert "Not provider verification" in report["notice"]
    assert output.exists()


CSV_HEADER = ("ProviderID,SiteName,ServiceType,StreetAddress,Lat,Lng,"
              "Publisher,PublisherURL,CheckedOn,Hours")
CSV_ROW = ('hc-101,Hope Center,shelter,"100 Example Ave, Minneapolis",44.98,-93.27,'
           "Hennepin County,https://example.org/hc-101,2026-10-20T12:00:00-05:00,"
           "Mon-Fri 9 AM-5 PM")


def write_csv(path, text):
    path.write_bytes(text.encode("utf-8"))
    return path


CSV_MAPPING = {**MAPPING, "hours": "Hours"}


def test_csv_export_ingests_through_the_same_validation(tmp_path):
    source = write_csv(tmp_path / "export.csv", CSV_HEADER + "\n" + CSV_ROW + "\n")
    report = ingest_records(read_provider_records(source), CSV_MAPPING)
    assert report["rejections"] == []
    (candidate,) = report["candidates"]
    assert candidate.id == "hc-101"
    assert candidate.name == "Hope Center"
    assert candidate.address == "100 Example Ave, Minneapolis"  # quoted comma survives
    assert candidate.latitude == 44.98 and candidate.longitude == -93.27
    assert candidate.hours[0] == [("09:00", "17:00")]  # provider text parsed strictly
    assert candidate.is_sample is True  # a text row can never assert review


def test_csv_with_byte_order_mark_parses(tmp_path):
    source = tmp_path / "export.csv"
    source.write_bytes(("\ufeff" + CSV_HEADER + "\n" + CSV_ROW + "\n").encode("utf-8"))
    report = ingest_records(read_provider_records(source), MAPPING)
    assert report["rejections"] == [] and len(report["candidates"]) == 1


def test_csv_duplicate_column_names_fail_the_whole_file(tmp_path):
    source = write_csv(tmp_path / "export.csv", "A,A\n1,2\n")
    with pytest.raises(ValueError, match="duplicate column"):
        read_provider_records(source)


def test_csv_blank_column_name_fails_the_whole_file(tmp_path):
    source = write_csv(tmp_path / "export.csv", "A,,C\n1,2,3\n")
    with pytest.raises(ValueError, match="blank column"):
        read_provider_records(source)


def test_csv_ragged_row_fails_loudly_with_a_line_number(tmp_path):
    source = write_csv(tmp_path / "export.csv", "A,B\n1,2\n3,4,5\n")
    with pytest.raises(ValueError, match="row 3"):
        read_provider_records(source)


def test_csv_blank_lines_are_skipped_but_empty_cells_still_validate(tmp_path):
    source = write_csv(tmp_path / "export.csv",
                       CSV_HEADER + "\n\n" + CSV_ROW + "\n\n")
    report = ingest_records(read_provider_records(source), MAPPING)
    assert len(report["candidates"]) == 1 and report["rejections"] == []


def test_csv_header_only_and_empty_files_fail_loudly(tmp_path):
    with pytest.raises(ValueError, match="no records"):
        read_provider_records(write_csv(tmp_path / "headers.csv", CSV_HEADER + "\n"))
    with pytest.raises(ValueError, match="header row"):
        read_provider_records(write_csv(tmp_path / "empty.csv", ""))


def test_csv_respects_the_same_byte_limit(tmp_path):
    source = write_csv(tmp_path / "big.csv",
                       CSV_HEADER + "\n" + "x" * (2 * 1024 * 1024) + "\n")
    with pytest.raises(ValueError, match="byte limit"):
        read_provider_records(source)


def test_csv_dirty_row_rejects_itself_and_keeps_the_batch(tmp_path):
    bad_row = CSV_ROW.replace("44.98", "not-a-number")
    source = write_csv(tmp_path / "export.csv",
                       CSV_HEADER + "\n" + bad_row + "\n" + CSV_ROW.replace("hc-101", "hc-102") + "\n")
    report = ingest_records(read_provider_records(source), MAPPING)
    assert len(report["rejections"]) == 1
    assert [item.id for item in report["candidates"]] == ["hc-102"]


def test_cli_accepts_a_csv_export(tmp_path):
    source = write_csv(tmp_path / "export.csv", CSV_HEADER + "\n" + CSV_ROW + "\n")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps(MAPPING), encoding="utf-8")
    output = tmp_path / "candidate.json"
    result = subprocess.run(
        [sys.executable, "-m", "app.ingest", str(source), str(mapping), str(output)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["candidate_count"] == 1 and report["rejection_count"] == 0
    assert [item.id for item in load_resources(output)] == ["hc-101"]
