"""A provider snapshot must pass validation before it can enter the directory."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.data import DATA_PATH, load_resources
from app.models import Resource
from app.search import find_resources, is_open


def record():
    return json.loads(DATA_PATH.read_text())[0]


def snapshot(tmp_path, data):
    path = tmp_path / "resources.json"
    path.write_text(json.dumps(data))
    return path


def test_explicit_path_and_environment_path(tmp_path, monkeypatch):
    data = record()
    data.update(id="provider-test", is_sample=False)
    path = snapshot(tmp_path, [data])
    assert load_resources(path)[0].id == "provider-test"
    monkeypatch.setenv("SHELTERLINK_DATA_PATH", str(path))
    assert load_resources()[0].id == "provider-test"
    assert load_resources(DATA_PATH)[0].is_sample


def test_missing_sample_marker_stays_non_live(tmp_path):
    data = record()
    del data["is_sample"]
    item = load_resources(snapshot(tmp_path, [data]))[0]
    assert item.is_sample is True
    at = item.verified_at
    assert not find_resources([item], item.latitude, item.longitude, at=at)[0].open_now


@pytest.mark.parametrize("data", [{"resources": []}, "bad", None, 42])
def test_snapshot_must_be_an_array(tmp_path, data):
    with pytest.raises(ValueError, match="JSON array"):
        load_resources(snapshot(tmp_path, data))


def test_duplicate_id_rejects_whole_snapshot(tmp_path):
    with pytest.raises(ValueError, match="duplicate IDs"):
        load_resources(snapshot(tmp_path, [record(), record()]))


def test_one_bad_record_rejects_whole_snapshot(tmp_path):
    bad = record()
    bad.update(id="bad", latitude=91)
    with pytest.raises(ValidationError):
        load_resources(snapshot(tmp_path, [record(), bad]))


@pytest.mark.parametrize("value", ["2026-09-30T12:00:00", "not-a-date"])
def test_verification_requires_aware_timestamp(value):
    data = record()
    data["verified_at"] = value
    with pytest.raises(ValidationError):
        Resource.model_validate(data)


@pytest.mark.parametrize("field", ["id", "name", "address", "source_name"])
def test_blank_identity_and_provenance_rejected(field):
    data = record()
    data[field] = "   "
    with pytest.raises(ValidationError, match="blank"):
        Resource.model_validate(data)


@pytest.mark.parametrize("hours", [
    {"7": [["08:00", "17:00"]]}, {"-1": [["08:00", "17:00"]]},
    {"0": [["8:00", "17:00"]]}, {"0": [["08:60", "17:00"]]},
    {"0": [["24:00", "24:00"]]}, {"0": [["08:00", "24:01"]]},
    {"0": [["17:00", "08:00"]]}, {"0": [["08:00", "08:00"]]},
])
def test_malformed_and_unsplit_overnight_hours_rejected(hours):
    data = record()
    data["hours"] = hours
    with pytest.raises(ValidationError):
        Resource.model_validate(data)


def test_full_day_and_split_overnight_hours():
    data = record()
    data["hours"] = {"0": [["22:00", "24:00"]], "1": [["00:00", "02:00"]]}
    item = Resource.model_validate(data)
    tz = ZoneInfo("America/Chicago")
    assert is_open(item, datetime(2026, 9, 21, 23, 59, tzinfo=tz))
    assert is_open(item, datetime(2026, 9, 22, 0, 0, tzinfo=tz))
    assert not is_open(item, datetime(2026, 9, 22, 2, 0, tzinfo=tz))
    data["hours"] = {"0": [["00:00", "24:00"]]}
    assert is_open(Resource.model_validate(data), datetime(2026, 9, 21, 23, 59, tzinfo=tz))


def test_unreadable_snapshot_never_falls_back_to_samples(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_resources(tmp_path / "missing.json")
    path = tmp_path / "invalid.json"
    path.write_text("{unfinished")
    with pytest.raises(json.JSONDecodeError):
        load_resources(path)


def test_trimmed_duplicate_ids_are_rejected(tmp_path):
    first, second = record(), record()
    second["id"] = "  " + first["id"] + "  "
    with pytest.raises(ValueError, match="duplicate IDs"):
        load_resources(snapshot(tmp_path, [first, second]))
