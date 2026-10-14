"""Misspelled snapshot fields are review blockers, not silently dropped data."""
import json

import pytest

from app.data import DATA_PATH, load_resources
from app.models import Resource


@pytest.mark.parametrize("field,value", [("availabilty", "full"), ("verified_on", "2026-10-14"),
                                       ("is_sampel", False), ("latitdue", 44.9),
                                       ("source_Url", "https://example.com"), ("notes", "private")])
def test_unknown_fields_reject_entire_snapshot(tmp_path, field, value):
    data = json.loads(DATA_PATH.read_text())
    data[-1][field] = value
    path = tmp_path / "resources.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        load_resources(path)


def test_known_fields_and_missing_optional_defaults_are_supported():
    data = json.loads(DATA_PATH.read_text())[0]
    for field in ("phone", "website", "hours", "availability", "is_sample"):
        data.pop(field, None)
    item = Resource.model_validate(data)
    assert item.is_sample and item.availability.value == "unknown"
    assert item.phone is None and item.website is None and item.hours == {}


def test_bundled_snapshot_round_trips_without_losing_fields():
    for item in load_resources():
        assert Resource.model_validate(item.model_dump()).model_dump() == item.model_dump()
