"""Ambiguous weekly intervals must be reviewed rather than silently accepted."""
import json

import pytest

from app.data import DATA_PATH, load_resources
from app.models import Resource


def record(hours):
    data = json.loads(DATA_PATH.read_text())[0]
    data["hours"] = hours
    return data


@pytest.mark.parametrize("intervals", [
    [["08:00", "12:00"], ["11:00", "15:00"]],
    [["11:00", "15:00"], ["08:00", "12:00"]],
    [["08:00", "17:00"], ["09:00", "10:00"]],
    [["08:00", "12:00"], ["08:00", "12:00"]],
    [["00:00", "24:00"], ["23:00", "24:00"]],
])
def test_overlap_nested_duplicate_and_unsorted_intervals_rejected(intervals):
    with pytest.raises(ValueError, match="overlap"):
        Resource.model_validate(record({"0": intervals}))


def test_adjacent_and_disjoint_intervals_keep_input_order():
    intervals = [["13:00", "17:00"], ["08:00", "12:00"], ["12:00", "13:00"]]
    item = Resource.model_validate(record({"0": intervals}))
    assert item.hours[0] == [tuple(interval) for interval in intervals]


def test_identical_times_on_different_weekdays_are_valid():
    assert Resource.model_validate(record({"0": [["08:00", "12:00"]],
                                           "1": [["08:00", "12:00"]]}))


def test_split_overnight_remains_valid():
    assert Resource.model_validate(record({"0": [["22:00", "24:00"]],
                                           "1": [["00:00", "02:00"]]}))


def test_one_overlap_rejects_whole_file(tmp_path):
    valid = record({"0": [["08:00", "12:00"]]})
    invalid = record({"0": [["08:00", "12:00"], ["09:00", "13:00"]]})
    invalid["id"] = "invalid"
    path = tmp_path / "resources.json"
    path.write_text(json.dumps([valid, invalid]))
    with pytest.raises(ValueError, match="overlap"):
        load_resources(path)
