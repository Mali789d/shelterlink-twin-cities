"""A review event must update the seed and its history as one consistent operation."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.history import read_history, verify_history
from app.models import Resource
from app.seed_review import main, record_review

# Times derive from now so future/predate checks stay stable whenever CI runs.
AT = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)
OLD = AT - timedelta(hours=30)


def _record(rid, verified_at=OLD, is_sample=False):
    return Resource.model_validate({
        "id": rid, "name": f"Site {rid}", "category": "shelter",
        "address": "1 Main St, Minneapolis, MN 55401",
        "latitude": 44.98, "longitude": -93.27, "phone": "(612) 555-0100",
        "source_name": "Provider", "source_url": f"https://example.org/{rid}",
        "verified_at": verified_at.isoformat(), "is_sample": is_sample,
    })


def _write_snapshot(tmp_path, *resources):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps([json.loads(r.model_dump_json()) for r in resources],
                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _verified_at(snapshot, rid):
    data = {r["id"]: r for r in json.loads(snapshot.read_text(encoding="utf-8"))}
    return datetime.fromisoformat(data[rid]["verified_at"].replace("Z", "+00:00"))


def test_record_review_redates_named_records_and_anchors(tmp_path):
    snapshot = _write_snapshot(tmp_path, _record("a"), _record("b"))
    history = tmp_path / "history.jsonl"
    result = record_review(snapshot, history, {"a"}, "re-checked a against its provider page", AT)
    assert _verified_at(snapshot, "a") == AT
    assert _verified_at(snapshot, "b") == OLD
    records = read_history(history)
    assert len(records) == 1
    assert records[0]["note"] == "re-checked a against its provider page"
    assert records[0]["resource_count"] == 2
    anchor = verify_history(history, snapshot, at=AT)
    assert anchor["chain_ok"] and anchor["snapshot_matches_latest"]
    assert result["reverified"] == ["a"]
    assert result["history_record"]["recorded_at"]


def test_record_review_chains_sequential_reviews(tmp_path):
    snapshot = _write_snapshot(tmp_path, _record("a"), _record("b"))
    history = tmp_path / "history.jsonl"
    record_review(snapshot, history, {"a"}, "first review", AT)
    later = AT + timedelta(hours=1)
    record_review(snapshot, history, {"a", "b"}, "second review", later)
    records = read_history(history)
    assert len(records) == 2
    assert records[0]["note"] == "first review"
    assert records[1]["note"] == "second review"
    anchor = verify_history(history, snapshot, at=later)
    assert anchor["chain_ok"] and anchor["snapshot_matches_latest"]


def test_record_review_rejects_unknown_ids_without_touching_files(tmp_path):
    snapshot = _write_snapshot(tmp_path, _record("a"))
    history = tmp_path / "history.jsonl"
    original = snapshot.read_bytes()
    with pytest.raises(ValueError, match="unknown"):
        record_review(snapshot, history, {"ghost"}, "note", AT)
    assert snapshot.read_bytes() == original
    assert not history.exists()


def test_record_review_never_redates_samples(tmp_path):
    snapshot = _write_snapshot(tmp_path, _record("s", is_sample=True))
    history = tmp_path / "history.jsonl"
    original = snapshot.read_bytes()
    with pytest.raises(ValueError, match="sample"):
        record_review(snapshot, history, {"s"}, "note", AT)
    assert snapshot.read_bytes() == original
    assert not history.exists()


def test_record_review_requires_an_explaining_note(tmp_path):
    snapshot = _write_snapshot(tmp_path, _record("a"))
    history = tmp_path / "history.jsonl"
    original = snapshot.read_bytes()
    with pytest.raises(ValueError, match="note"):
        record_review(snapshot, history, {"a"}, "   ", AT)
    with pytest.raises(ValueError, match="note"):
        record_review(snapshot, history, {"a"}, "x" * 281, AT)
    assert snapshot.read_bytes() == original
    assert not history.exists()


def test_record_review_rejects_future_and_retroactive_times(tmp_path):
    snapshot = _write_snapshot(tmp_path, _record("a"))
    history = tmp_path / "history.jsonl"
    original = snapshot.read_bytes()
    future = datetime.now(timezone.utc) + timedelta(days=1)
    with pytest.raises(ValueError, match="future"):
        record_review(snapshot, history, {"a"}, "note", future)
    record_review(snapshot, history, {"a"}, "first review", AT)
    with pytest.raises(ValueError, match="backwards"):
        record_review(snapshot, history, {"a"}, "retro review", AT - timedelta(hours=1))
    assert len(read_history(history)) == 1
    assert _verified_at(snapshot, "a") == AT
    assert snapshot.read_bytes() != original


def test_record_review_rejects_time_before_the_latest_history_record(tmp_path):
    # A review dated before the chain's latest record falsifies the review
    # order, even when the named record itself could legitimately be re-dated.
    snapshot = _write_snapshot(tmp_path, _record("a"), _record("b"))
    history = tmp_path / "history.jsonl"
    record_review(snapshot, history, {"a"}, "first review", AT)
    with pytest.raises(ValueError, match="predate"):
        record_review(snapshot, history, {"b"}, "retro review", AT - timedelta(hours=1))
    assert len(read_history(history)) == 1
    assert _verified_at(snapshot, "b") == OLD


def test_record_review_refuses_a_drifted_snapshot(tmp_path):
    # A seed edited without a history append fails the anchor test; the next
    # review must refuse instead of papering over the drift with a new record.
    snapshot = _write_snapshot(tmp_path, _record("a"))
    history = tmp_path / "history.jsonl"
    record_review(snapshot, history, {"a"}, "first review", AT)
    drifted = _write_snapshot(tmp_path, _record("a"), _record("b"))
    drifted_bytes = drifted.read_bytes()
    with pytest.raises(ValueError, match="drifted"):
        record_review(drifted, history, {"a"}, "second review", AT + timedelta(hours=1))
    assert drifted.read_bytes() == drifted_bytes
    assert len(read_history(history)) == 1


def test_record_review_restores_snapshot_when_history_write_fails(tmp_path, monkeypatch):
    snapshot = _write_snapshot(tmp_path, _record("a"))
    history = tmp_path / "history.jsonl"
    original = snapshot.read_bytes()

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("app.seed_review.append_record", boom)
    with pytest.raises(RuntimeError, match="disk full"):
        record_review(snapshot, history, {"a"}, "note", AT)
    assert snapshot.read_bytes() == original
    assert not history.exists()


def test_record_review_cli_roundtrip(tmp_path, capsys, monkeypatch):
    snapshot = _write_snapshot(tmp_path, _record("a"))
    history = tmp_path / "history.jsonl"
    monkeypatch.setattr("sys.argv", [
        "seed_review", str(snapshot), "--history", str(history),
        "--checked", "a", "--note", "operator re-check", "--at", AT.isoformat(),
    ])
    main()
    printed = json.loads(capsys.readouterr().out)
    assert printed["reverified"] == ["a"]
    assert printed["history_record"]["note"] == "operator re-check"
    anchor = verify_history(history, snapshot, at=AT)
    assert anchor["chain_ok"] and anchor["snapshot_matches_latest"]


@pytest.mark.parametrize('damage', ['blank_note', 'boolean_count', 'wrong_count'])
def test_review_rejects_bad_history_metadata_before_any_write(tmp_path, damage):
    snapshot = _write_snapshot(tmp_path, _record('a'))
    history = tmp_path / 'history.jsonl'
    record_review(snapshot, history, {'a'}, 'first review', AT)
    record = json.loads(history.read_text())
    if damage == 'blank_note':
        record['note'] = ' '
    elif damage == 'boolean_count':
        record['resource_count'] = True
    else:
        record['resource_count'] = 999
    history.write_text(json.dumps(record) + '\n', encoding='utf-8')
    before = snapshot.read_bytes(), history.read_bytes()
    with pytest.raises(ValueError, match='history line 1|resource_count'):
        record_review(snapshot, history, {'a'}, 'next review', AT + timedelta(hours=1))
    assert (snapshot.read_bytes(), history.read_bytes()) == before
    assert not list(tmp_path.glob('tmp*'))
