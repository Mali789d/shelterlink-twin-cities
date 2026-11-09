"""Record a source re-check and its history entry as one consistent operation.

Re-verification moves ``verified_at`` for records the operator re-checked
against their own sources, and the append-only history must anchor every seed
change (tests/test_seed_history.py enforces that anchor). Run as two separate
commands, a failed or forgotten append leaves the tree in a state CI rejects:
the seed moved but no record explains it. This module validates everything
before any write, then performs both steps, restoring the original snapshot
bytes if the history append cannot complete, so the tree never sits
half-updated.

Both steps record the operator's assertion only. Nothing here proves a
provider check happened; an unchecked record must keep its old date and go
stale on schedule.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .data import load_resources
from .history import (MAX_NOTE_LENGTH, append_record, read_history,
                      snapshot_digest, verify_history)
from .reverify import reverify, serialize_resources, write_snapshot_atomically


def _aware(at: datetime) -> datetime:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("review time must include a timezone")
    return at


def _instant(value: str) -> datetime:
    # read_history already validated the timestamp text and its timezone.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def record_review(snapshot_path, history_path, checked_ids, note, at) -> dict:
    """Re-date the re-checked records and append the anchoring history record.

    Every check that can fail runs before the first write: unknown or sample
    records, an unexplained or oversized note, a naive, future or retroactive
    review time, a broken existing chain, and a snapshot that has drifted from
    its latest history record all refuse with both files untouched. After the
    snapshot write, a history write that still fails (an IO race) restores the
    original snapshot bytes before the error propagates.
    """
    snapshot_path, history_path = Path(snapshot_path), Path(history_path)
    if history_path.resolve() == snapshot_path.resolve() or (
            history_path.exists() and snapshot_path.samefile(history_path)):
        raise ValueError("history output must not replace the snapshot it records")
    at = _aware(at)
    if at.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("review cannot be dated in the future")
    note = (note or "").strip()
    if not note:
        raise ValueError("review note must explain the re-check")
    if len(note) > MAX_NOTE_LENGTH:
        raise ValueError("review note exceeds length limit")

    resources = load_resources(snapshot_path)
    updated = reverify(resources, set(checked_ids), at)
    records = read_history(history_path)
    if records:
        latest = max(_instant(record["recorded_at"]) for record in records)
        if at.astimezone(timezone.utc) < latest:
            raise ValueError("review cannot predate the latest history record")
        anchor = verify_history(history_path, snapshot_path, at=at)
        if not anchor["chain_ok"]:
            raise ValueError("refusing to extend broken history: "
                             + "; ".join(anchor["problems"]))
        if not anchor["snapshot_matches_latest"]:
            raise ValueError(
                "snapshot has drifted from its latest history record; "
                "record or revert that change before reviewing again")
        if records[-1]["snapshot_sha256"] == snapshot_digest(updated):
            raise ValueError("snapshot is unchanged since the latest history record")

    original = snapshot_path.read_bytes()
    write_snapshot_atomically(snapshot_path, serialize_resources(updated))
    try:
        record = append_record(history_path, snapshot_path, note, at)
    except Exception:
        # Restore so the tree never fails its own anchor test after a crash.
        write_snapshot_atomically(snapshot_path, original.decode("utf-8"))
        raise
    return {"reverified": sorted(set(checked_ids)), "history_record": record}


def main():
    parser = argparse.ArgumentParser(
        description="Record re-checked records and their history entry in one operation")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--history", type=Path, required=True,
                        help="append-only history log to anchor the updated snapshot")
    parser.add_argument("--checked", action="append", required=True, metavar="ID",
                        help="record ID re-checked against its source_url; repeat per record")
    parser.add_argument("--note", required=True,
                        help="what the operator re-checked, in their own words")
    parser.add_argument("--at", type=datetime.fromisoformat,
                        default=datetime.now(timezone.utc),
                        help="review instant, ISO 8601 with timezone (default: now)")
    args = parser.parse_args()
    result = record_review(args.snapshot, args.history, args.checked, args.note, args.at)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
