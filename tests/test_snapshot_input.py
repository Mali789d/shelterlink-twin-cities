"""Reject ambiguous and oversized imported JSON before resource validation."""
import json

import pytest

from app.data import MAX_SNAPSHOT_BYTES, load_resources


def test_exact_byte_limit_allows_valid_empty_snapshot(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(b"[]" + b" " * (MAX_SNAPSHOT_BYTES - 2))
    assert load_resources(path) == []


def test_actual_bytes_above_limit_reject_even_valid_json(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(b"[]" + b" " * (MAX_SNAPSHOT_BYTES - 1))
    with pytest.raises(ValueError, match="byte limit"):
        load_resources(path)


@pytest.mark.parametrize("text", [
    '[{"is_sample":true,"is_sample":false}]',
    '[{"latitude":91,"latitude":44.9}]',
    '[{"source_url":"https://bad.example","source_url":"https://example.com"}]',
    '[{"hours":{"0":[],"0":[["08:00","09:00"]]}}]',
    '[{"id":"a","\\u0069d":"b"}]',
])
def test_duplicate_keys_cannot_silently_override_provenance_or_validation(tmp_path, text):
    path = tmp_path / "input.json"
    path.write_text(text)
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        load_resources(path)


def test_invalid_utf8_is_not_repaired(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(b'[{"name":"\xff"}]')
    with pytest.raises(UnicodeDecodeError):
        load_resources(path)


def test_distinct_resources_can_use_the_same_field_names(tmp_path):
    from app.data import DATA_PATH
    data = json.loads(DATA_PATH.read_text())
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data))
    assert len(load_resources(path)) == len(data)
