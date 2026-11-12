"""Change history is append-only, explained, and tamper-evident."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from app.history import (MAX_NOTE_LENGTH, _record_digest, append_record, read_history,
                         snapshot_digest, verify_history)
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
    return json.dumps({"recorded_at": recorded_at, "snapshot_sha256": "a" * 64,
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


@pytest.mark.parametrize("damage", ["edit", "remove_first", "reorder", "bad_root", "bad_tail"])
def test_append_refuses_to_extend_broken_history_without_writing(tmp_path, damage):
    history = tmp_path / "history.jsonl"
    snapshots = [write_snapshot(tmp_path / f"v{i}.json", resource(name=f"Version {i}"))
                 for i in range(4)]
    for index in range(3):
        append_record(history, snapshots[index], f"Review {index}", at=AT)
    lines = [json.loads(line) for line in history.read_text().splitlines()]
    if damage == "edit":
        lines[0]["note"] = "Changed earlier note"
    elif damage == "remove_first":
        lines.pop(0)
    elif damage == "reorder":
        lines[0], lines[1] = lines[1], lines[0]
    elif damage == "bad_root":
        lines[0]["previous_sha256"] = "a" * 64
    else:
        lines[-1]["previous_sha256"] = "b" * 64
    history.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    before = history.read_bytes()
    snapshot_before = snapshots[-1].read_bytes()
    assert verify_history(history)["chain_ok"] is False
    with pytest.raises(ValueError, match="refusing to extend broken history: line"):
        append_record(history, snapshots[-1], "New review must not hide break", at=AT)
    assert history.read_bytes() == before
    assert snapshots[-1].read_bytes() == snapshot_before
    assert not list(tmp_path.glob("tmp*"))


def test_cli_refuses_broken_chain_and_preserves_it(tmp_path):
    history = tmp_path / "history.jsonl"
    snapshot = write_snapshot(tmp_path / "v1.json", resource())
    append_record(history, snapshot, "First review", at=AT)
    record = json.loads(history.read_text())
    record["previous_sha256"] = "a" * 64
    history.write_text(json.dumps(record) + "\n")
    before = history.read_bytes()
    changed = write_snapshot(tmp_path / "v2.json", resource(name="New version"))
    process = subprocess.run([sys.executable, "-m", "app.history", "append", str(changed),
        str(history), "--note", "New review"], capture_output=True, text=True)
    assert process.returncode != 0
    assert "refusing to extend broken history" in process.stderr
    assert history.read_bytes() == before


def test_valid_history_still_extends_after_read_only_mismatch(tmp_path):
    # A snapshot mismatch is not a broken link: recording a real changed snapshot
    # is the whole purpose of append. Keep these two checks separate.
    history = tmp_path / "history.jsonl"
    first = write_snapshot(tmp_path / "v1.json", resource())
    next_snapshot = write_snapshot(tmp_path / "v2.json", resource(name="New version"))
    append_record(history, first, "Initial", at=AT)
    assert verify_history(history, next_snapshot)["snapshot_matches_latest"] is False
    append_record(history, next_snapshot, "Reviewed changed snapshot", at=AT)
    report = verify_history(history, next_snapshot)
    assert report["chain_ok"] is True
    assert report["snapshot_matches_latest"] is True
    assert report["record_count"] == 2


def _hand_built_chain(times):
    """A hash-valid chain with chosen recorded_at values, built line by line.

    append_record refuses retro- and future-dated records, so the only way a
    time-incoherent chain exists is a rewrite that recomputed every link -
    exactly the tamper shape verification must catch.
    """
    records = []
    previous_digest = None
    for index, recorded_at in enumerate(times):
        record = {
            "recorded_at": recorded_at.isoformat(),
            "snapshot_sha256": hashlib.sha256(f"snapshot-{index}".encode()).hexdigest(),
            "resource_count": 1,
            "note": f"review {index}",
            "previous_sha256": previous_digest,
        }
        previous_digest = _record_digest(record)
        records.append(record)
    return records


def write_chain(path, records):
    path.write_text("".join(json.dumps(record) + "\n" for record in records),
                    encoding="utf-8")
    return path


def test_append_refuses_to_predate_the_latest_record_without_writing(tmp_path):
    history = tmp_path / "history.jsonl"
    first = write_snapshot(tmp_path / "v1.json", resource())
    append_record(history, first, "v1 review", at=AT)
    changed = write_snapshot(tmp_path / "v2.json", resource(name="New version"))
    before = history.read_bytes()
    with pytest.raises(ValueError, match="predate"):
        append_record(history, changed, "Back-dated review",
                      at=AT - timedelta(hours=1))
    assert history.read_bytes() == before
    assert not list(tmp_path.glob("tmp*"))


def test_append_allows_the_same_instant_as_the_latest_record(tmp_path):
    history = tmp_path / "history.jsonl"
    first = write_snapshot(tmp_path / "v1.json", resource())
    changed = write_snapshot(tmp_path / "v2.json", resource(name="New version"))
    append_record(history, first, "v1 review", at=AT)
    append_record(history, changed, "Same-clock review", at=AT)
    assert len(read_history(history)) == 2
    assert verify_history(history, changed)["chain_ok"] is True


def test_append_refuses_a_future_dated_record(tmp_path):
    history = tmp_path / "history.jsonl"
    snapshot = write_snapshot(tmp_path / "v1.json", resource())
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    with pytest.raises(ValueError, match="future"):
        append_record(history, snapshot, "Review from tomorrow", at=future)
    assert not history.exists()


def test_verify_flags_out_of_order_records_even_with_valid_links(tmp_path):
    history = tmp_path / "history.jsonl"
    early = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    later = early + timedelta(hours=6)
    write_chain(history, _hand_built_chain([later, early, later + timedelta(hours=6)]))
    result = verify_history(history, at=later + timedelta(days=1))
    assert result["chain_ok"] is False
    assert result["problems"] == ["line 2: recorded_at is earlier than a previous record"]
    # An out-of-order chain is a broken chain: appends refuse to extend it.
    snapshot = write_snapshot(tmp_path / "v1.json", resource())
    before = history.read_bytes()
    with pytest.raises(ValueError, match="refusing to extend broken history"):
        append_record(history, snapshot, "Must not hide the rewrite",
                      at=later + timedelta(days=2))
    assert history.read_bytes() == before


def test_verify_accepts_equal_timestamps_in_different_offsets(tmp_path):
    history = tmp_path / "history.jsonl"
    moment = datetime(2026, 10, 20, 17, 0, tzinfo=timezone.utc)
    same_moment_other_offset = datetime(2026, 10, 20, 12, 0,
                                        tzinfo=timezone(timedelta(hours=-5)))
    write_chain(history, _hand_built_chain([moment, same_moment_other_offset]))
    result = verify_history(history, at=moment + timedelta(days=1))
    assert result["chain_ok"] is True
    assert result["problems"] == []


def test_verify_flags_a_future_dated_record(tmp_path):
    history = tmp_path / "history.jsonl"
    past = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    future = datetime.now(timezone.utc) + timedelta(days=2)
    write_chain(history, _hand_built_chain([past, future]))
    result = verify_history(history)
    assert result["chain_ok"] is False
    assert result["problems"] == ["line 2: recorded_at is in the future"]
    # Verified from after that date, the same chain is time-coherent.
    later = verify_history(history, at=future + timedelta(days=1))
    assert later["chain_ok"] is True
    assert later["problems"] == []


def test_verify_rejects_a_naive_verification_time(tmp_path):
    history = write_chain(tmp_path / "history.jsonl", _hand_built_chain([AT]))
    with pytest.raises(ValueError, match="timezone"):
        verify_history(history, at=datetime(2026, 10, 29, 12, 0))


@pytest.mark.parametrize('field, value', [
    ('snapshot_sha256', 'x' * 64), ('snapshot_sha256', 'A' * 64),
    ('snapshot_sha256', 'a' * 63), ('snapshot_sha256', None),
    ('previous_sha256', ''), ('previous_sha256', ['a' * 64]),
    ('resource_count', True), ('resource_count', -1),
    ('resource_count', 1.0), ('resource_count', '1'),
    ('note', ''), ('note', '  '), ('note', 1), ('note', ['review']),
    ('note', 'x' * (MAX_NOTE_LENGTH + 1)), ('unexpected_claim', 'approved'),
])
def test_malformed_metadata_refuses_reads_verification_and_appends(tmp_path, field, value):
    snapshot = write_snapshot(tmp_path / 'snapshot.json', resource())
    changed = write_snapshot(tmp_path / 'changed.json', resource(name='Reviewed change'))
    history = tmp_path / 'history.jsonl'
    record = append_record(history, snapshot, 'Initial review', at=AT)
    record[field] = value
    history.write_text(json.dumps(record) + '\n', encoding='utf-8')
    before = history.read_bytes()
    snapshot_before = changed.read_bytes()
    for action in (lambda: read_history(history),
                   lambda: verify_history(history, snapshot),
                   lambda: append_record(history, changed, 'Next review', at=AT)):
        with pytest.raises(ValueError, match='history line 1'):
            action()
    assert history.read_bytes() == before
    assert changed.read_bytes() == snapshot_before
    assert not list(tmp_path.glob('tmp*'))


def test_validly_encoded_wrong_tail_count_fails_snapshot_anchor(tmp_path):
    snapshot = write_snapshot(tmp_path / 'snapshot.json', resource())
    history = tmp_path / 'history.jsonl'
    record = append_record(history, snapshot, 'Initial review', at=AT)
    record['resource_count'] = 999  # well-formed, but contradicts the hashed snapshot
    history.write_text(json.dumps(record) + '\n', encoding='utf-8')
    before = history.read_bytes()
    result = verify_history(history, snapshot, at=AT)
    assert result['snapshot_matches_latest'] is True
    assert result['chain_ok'] is False
    assert result['problems'] == ['line 1: resource_count does not match the anchored snapshot']
    # Without a snapshot, count truth cannot be checked. Do not pretend otherwise.
    assert verify_history(history, at=AT)['chain_ok'] is True
    assert history.read_bytes() == before


def test_zero_count_is_valid_for_an_empty_snapshot(tmp_path):
    snapshot = write_snapshot(tmp_path / 'snapshot.json')
    history = tmp_path / 'history.jsonl'
    append_record(history, snapshot, 'Reviewed removal of the last record', at=AT)
    assert read_history(history)[0]['resource_count'] == 0
    assert verify_history(history, snapshot, at=AT)['chain_ok'] is True


def test_cli_malformed_metadata_fails_without_changing_history(tmp_path):
    history = tmp_path / 'history.jsonl'
    snapshot = write_snapshot(tmp_path / 'snapshot.json', resource())
    record = append_record(history, snapshot, 'Initial review', at=AT)
    record['resource_count'] = True
    history.write_text(json.dumps(record) + '\n', encoding='utf-8')
    before = history.read_bytes()
    result = subprocess.run([sys.executable, '-m', 'app.history', 'verify',
                             str(history), str(snapshot)], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'history line 1: resource_count' in result.stderr
    assert history.read_bytes() == before


def _verify_cli(history, snapshot=None):
    args = [sys.executable, '-m', 'app.history', 'verify', str(history)]
    if snapshot is not None:
        args.append(str(snapshot))
    return subprocess.run(args, capture_output=True, text=True)


@pytest.mark.parametrize('damage', ['link', 'timeline', 'future', 'count', 'snapshot', 'empty'])
def test_verify_cli_failure_report_exits_nonzero_without_writes(tmp_path, damage):
    snapshot = write_snapshot(tmp_path / 'snapshot.json', resource())
    history = tmp_path / 'history.jsonl'
    record = append_record(history, snapshot, 'Initial review', at=AT)
    if damage == 'link':
        record['previous_sha256'] = 'a' * 64
    elif damage == 'future':
        record['recorded_at'] = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    elif damage == 'count':
        record['resource_count'] = 999
    if damage == 'timeline':
        write_chain(history, _hand_built_chain([AT, AT - timedelta(hours=1)]))
    elif damage == 'empty':
        history.write_text('', encoding='utf-8')
    else:
        history.write_text(json.dumps(record) + '\n', encoding='utf-8')
    if damage == 'snapshot':
        write_snapshot(snapshot, resource(name='Changed without review'))
    before = history.read_bytes(), snapshot.read_bytes()
    result = _verify_cli(history, snapshot)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert not report['chain_ok'] or report['snapshot_matches_latest'] is False
    assert result.stderr == ''  # ordinary failed checks are JSON, not tracebacks
    assert (history.read_bytes(), snapshot.read_bytes()) == before


def test_verify_cli_valid_anchor_and_chain_only_exit_success(tmp_path):
    snapshot = write_snapshot(tmp_path / 'snapshot.json', resource())
    history = tmp_path / 'history.jsonl'
    append_record(history, snapshot, 'Initial review', at=AT)
    anchored = _verify_cli(history, snapshot)
    assert anchored.returncode == 0
    assert json.loads(anchored.stdout)['snapshot_matches_latest'] is True
    chain_only = _verify_cli(history)
    assert chain_only.returncode == 0
    assert 'snapshot_matches_latest' not in json.loads(chain_only.stdout)


def test_verify_cli_broken_chain_without_snapshot_still_fails(tmp_path):
    history = write_chain(tmp_path / 'history.jsonl', _hand_built_chain([AT]))
    record = json.loads(history.read_text())
    record['previous_sha256'] = 'a' * 64
    history.write_text(json.dumps(record) + '\n', encoding='utf-8')
    result = _verify_cli(history)
    assert result.returncode == 1
    assert json.loads(result.stdout)['chain_ok'] is False


def test_verify_cli_missing_history_with_snapshot_fails_but_chain_only_is_empty(tmp_path):
    history = tmp_path / 'not-created.jsonl'
    snapshot = write_snapshot(tmp_path / 'snapshot.json', resource())
    anchored = _verify_cli(history, snapshot)
    assert anchored.returncode == 1
    assert 'history is empty' in json.loads(anchored.stdout)['problems']
    assert _verify_cli(history).returncode == 0
    assert not history.exists()
