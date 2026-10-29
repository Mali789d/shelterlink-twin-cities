"""Change history is append-only, explained, and tamper-evident."""
import json
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from app.history import (MAX_NOTE_LENGTH, append_record, read_history, snapshot_digest,
                         verify_history)
from app.models import Resource

AT = datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc)


def write_snapshot(path, *resources):
    path.write_text(json.dumps(list(resources)), encoding="utf-8")
    return path


def resource(resource_id="hc-101", name="Hope Center", **overrides):
    record = {
        "id": resource_id, "name": name, "category": "shelter",
        "address": "100 Example Ave, Minneapolis", "latitude": 44.98, "longitude": -93.27,
        "source_name": "Hennepin County", "source_url": "https://example.org/hc",
        "verified_at": "2026-10-20T12:00:00-05:00", "is_sample": True,
    }
    record.update(overrides)
    return record


def test_first_record_chains_from_null_and_hashes_the_snapshot(tmp_path):
    snapshot = write_snapshot(tmp_path / "resources.json", resource())
    history = tmp_path / "history.jsonl"
    record = append_record(history, snapshot, "Adopted the October provider review", at=AT)
    assert record["previous_sha256"] is None
    assert record["resource_count"] == 1
    assert record["snapshot_sha256"] == snapshot_digest([Resource.model_validate(resource())])
    assert verify_history(history, snapshot)["chain_ok"] is True
    assert verify_history(history, snapshot)["snapshot_matches_latest"] is True


def test_digest_ignores_file_formatting_and_key_order(tmp_path):
    first = write_snapshot(tmp_path / "a.json", resource())
    reordered = dict(reversed(list(resource().items())))
    second = tmp_path / "b.json"
    second.write_text(json.dumps([reordered], indent=4), encoding="utf-8")
    history = tmp_path / "history.jsonl"
    append_record(history, first, "First review", at=AT)
    with pytest.raises(ValueError, match="unchanged"):
        append_record(history, second, "Same content, new formatting", at=AT)


def test_chain_links_each_record_to_the_previous(tmp_path):
    history = tmp_path / "history.jsonl"
    first = write_snapshot(tmp_path / "v1.json", resource())
    append_record(history, first, "v1 review", at=AT)
    second = write_snapshot(tmp_path / "v2.json", resource(), resource("hc-102", "Second Site"))
    append_record(history, second, "Added hc-102", at=AT)
    records = read_history(history)
    assert len(records) == 2
    assert records[1]["previous_sha256"] != records[0]["previous_sha256"]
    assert verify_history(history, second)["chain_ok"] is True


def test_edited_earlier_record_breaks_the_chain_at_a_named_line(tmp_path):
    history = tmp_path / "history.jsonl"
    one = write_snapshot(tmp_path / "v1.json", resource())
    two = write_snapshot(tmp_path / "v2.json", resource(), resource("hc-102", "Second Site"))
    append_record(history, one, "v1 review", at=AT)
    append_record(history, two, "Added hc-102", at=AT)
    lines = history.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["note"] = "quietly rewritten"
    lines[0] = json.dumps(tampered)
    history.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_history(history)
    assert result["chain_ok"] is False
    assert result["problems"] == ["line 2: previous link does not match the earlier record"]


def test_snapshot_mismatch_against_latest_record_is_reported(tmp_path):
    history = tmp_path / "history.jsonl"
    one = write_snapshot(tmp_path / "v1.json", resource())
    append_record(history, one, "v1 review", at=AT)
    changed = write_snapshot(tmp_path / "v1b.json", resource(name="Renamed Center"))
    result = verify_history(history, changed)
    assert result["chain_ok"] is True  # chain itself is intact
    assert result["snapshot_matches_latest"] is False


def test_no_op_append_is_refused_and_file_untouched(tmp_path):
    snapshot = write_snapshot(tmp_path / "resources.json", resource())
    history = tmp_path / "history.jsonl"
    append_record(history, snapshot, "v1 review", at=AT)
    before = history.read_bytes()
    with pytest.raises(ValueError, match="unchanged"):
        append_record(history, snapshot, "No actual change", at=AT)
    assert history.read_bytes() == before


def test_blank_and_overlong_notes_are_refused(tmp_path):
    snapshot = write_snapshot(tmp_path / "resources.json", resource())
    history = tmp_path / "history.jsonl"
    with pytest.raises(ValueError, match="explain"):
        append_record(history, snapshot, "   ")
    with pytest.raises(ValueError, match="length"):
        append_record(history, snapshot, "x" * (MAX_NOTE_LENGTH + 1))
    assert not history.exists()


def test_invalid_snapshot_never_touches_the_history(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([resource(latitude=999)]), encoding="utf-8")
    history = tmp_path / "history.jsonl"
    with pytest.raises(ValueError):
        append_record(history, bad, "Should not land")
    assert not history.exists()


def test_history_never_replaces_its_snapshot(tmp_path):
    snapshot = write_snapshot(tmp_path / "resources.json", resource())
    with pytest.raises(ValueError, match="must not replace"):
        append_record(snapshot, snapshot, "Self-referential")


def test_malformed_history_line_fails_loudly(tmp_path):
    history = tmp_path / "history.jsonl"
    history.write_text('{"note": "incomplete"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        read_history(history)


def test_verify_without_snapshot_checks_chain_only_and_empty_history(tmp_path):
    history = tmp_path / "history.jsonl"
    result = verify_history(history)
    assert result == {"notice": result["notice"], "record_count": 0, "problems": [],
                      "chain_ok": True}
    anchored = verify_history(history, write_snapshot(tmp_path / "r.json", resource()))
    assert anchored["chain_ok"] is False and "history is empty" in anchored["problems"]


def test_cli_append_then_verify_round_trip(tmp_path):
    snapshot = write_snapshot(tmp_path / "resources.json", resource())
    history = tmp_path / "history.jsonl"
    appended = subprocess.run(
        [sys.executable, "-m", "app.history", "append", str(snapshot), str(history),
         "--note", "Adopted October review"],
        capture_output=True, text=True, check=True)
    assert json.loads(appended.stdout)["appended"]["resource_count"] == 1
    verified = subprocess.run(
        [sys.executable, "-m", "app.history", "verify", str(history), str(snapshot)],
        capture_output=True, text=True, check=True)
    report = json.loads(verified.stdout)
    assert report["chain_ok"] is True and report["snapshot_matches_latest"] is True
    assert "Not provider verification" in report["notice"]


def _record_line(recorded_at):
    return json.dumps({"recorded_at": recorded_at, "snapshot_sha256": "x" * 64,
                       "resource_count": 1, "note": "review", "previous_sha256": None})


@pytest.mark.parametrize("recorded_at", [
    "yesterday",                    # not a timestamp at all
    "2026-10-20T12:00:00",          # naive: no timezone to order the review by
    "2026-13-01T12:00:00Z",         # impossible month
    12345,                          # not even text
])
def test_history_rejects_records_without_aware_timestamps(tmp_path, recorded_at):
    history = tmp_path / "history.jsonl"
    history.write_text(_record_line(recorded_at) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_history(history)


@pytest.mark.parametrize("recorded_at", ["2026-10-20T12:00:00-05:00", "2026-10-20T17:00:00Z"])
def test_history_accepts_timezone_bearing_timestamps(tmp_path, recorded_at):
    history = tmp_path / "history.jsonl"
    history.write_text(_record_line(recorded_at) + "\n", encoding="utf-8")
    (record,) = read_history(history)
    assert record["recorded_at"] == recorded_at


def test_append_rejects_a_naive_timestamp(tmp_path):
    history = tmp_path / "history.jsonl"
    snapshot = write_snapshot(tmp_path / "snapshot.json", resource())
    with pytest.raises(ValueError):
        append_record(history, snapshot, "review", at=datetime(2026, 10, 29, 12, 0))
    assert not history.exists()
