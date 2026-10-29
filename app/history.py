"""Append-only, tamper-evident change history for reviewed directory snapshots.

Each record hashes the full snapshot plus the previous record, so editing or
reordering any earlier record breaks the chain at a checkable line. A local
chain cannot prove the unanchored tail on its own: verifying against the
current snapshot anchors the latest record's content, and version control
covers the rest. History records operator review events only - never provider
verification, availability, or publication approval.
"""
import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .data import MAX_SNAPSHOT_BYTES, load_resources, unique_object

MAX_HISTORY_BYTES = MAX_SNAPSHOT_BYTES
MAX_NOTE_LENGTH = 280

RECORD_FIELDS = ("recorded_at", "snapshot_sha256", "resource_count", "note", "previous_sha256")


def snapshot_digest(resources) -> str:
    """Stable digest over canonical resource data, independent of file formatting."""
    canonical = json.dumps([item.model_dump(mode="json") for item in resources],
                           ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical(record) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_digest(record) -> str:
    return hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()


def _aware_instant(value, label: str) -> None:
    """A record's time is part of its evidence: ISO text with a timezone, or
    the record cannot order the review it claims to document. Naive or
    unparseable timestamps reject the line, like any other malformed field."""
    if not isinstance(value, str):
        raise ValueError(f"{label}: recorded_at must be an ISO timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{label}: recorded_at is not an ISO timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label}: recorded_at must include a timezone")


def read_history(path) -> list:
    """Parse a history log, bounding bytes and validating each record's shape."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open("rb") as history_file:
        raw = history_file.read(MAX_HISTORY_BYTES + 1)
    if len(raw) > MAX_HISTORY_BYTES:
        raise ValueError("change history exceeds byte limit")
    records = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line, object_pairs_hook=unique_object)
        if not isinstance(record, dict) or any(field not in record for field in RECORD_FIELDS):
            raise ValueError(f"history line {line_number} is not a complete record object")
        _aware_instant(record["recorded_at"], f"history line {line_number}")
        records.append(record)
    return records


def append_record(history_path, snapshot_path, note, at=None) -> dict:
    """Record one reviewed snapshot, refusing no-op and unexplained entries."""
    history_path, snapshot_path = Path(history_path), Path(snapshot_path)
    note = (note or "").strip()
    if not note:
        raise ValueError("history note must explain the change")
    if len(note) > MAX_NOTE_LENGTH:
        raise ValueError("history note exceeds length limit")
    # Never let the log replace its own snapshot, even through links or aliases.
    if history_path.resolve() == snapshot_path.resolve() or (
            history_path.exists() and snapshot_path.samefile(history_path)):
        raise ValueError("history output must not replace the snapshot it records")
    # Validate the snapshot fully before the history file is read or written.
    resources = load_resources(snapshot_path)
    digest = snapshot_digest(resources)
    records = read_history(history_path)
    previous = records[-1] if records else None
    if previous and previous["snapshot_sha256"] == digest:
        raise ValueError("snapshot is unchanged since the latest history record")
    if at is not None and (at.tzinfo is None or at.utcoffset() is None):
        # A naive clock value would write a timestamp that reads as a broken chain.
        raise ValueError("history timestamp must include a timezone")
    recorded_at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    record = {
        "recorded_at": recorded_at.isoformat(),
        "snapshot_sha256": digest,
        "resource_count": len(resources),
        "note": note,
        "previous_sha256": _record_digest(previous) if previous else None,
    }
    existing = history_path.read_text(encoding="utf-8") if history_path.exists() else ""
    separator = "" if not existing or existing.endswith("\n") else "\n"
    text = existing + separator + _canonical(record) + "\n"
    if len(text.encode("utf-8")) > MAX_HISTORY_BYTES:
        raise ValueError("change history exceeds byte limit")
    # Atomic whole-file rewrite: an interrupted append never leaves a half-line
    # that would read as a broken chain.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=history_path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
        os.replace(temporary, history_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return record


def verify_history(history_path, snapshot_path=None) -> dict:
    """Check chain integrity and, optionally, anchor the tail to a live snapshot."""
    records = read_history(history_path)
    problems = []
    previous_digest = None
    for index, record in enumerate(records):
        if record["previous_sha256"] != previous_digest:
            problems.append(f"line {index + 1}: previous link does not match the earlier record")
        previous_digest = _record_digest(record)
    result = {
        "notice": "History integrity review only. Not provider verification or publication approval.",
        "record_count": len(records),
        "problems": problems,
        "chain_ok": not problems,
    }
    if snapshot_path is not None:
        if not records:
            result["chain_ok"] = False
            result["snapshot_matches_latest"] = False
            result["problems"].append("history is empty")
        else:
            digest = snapshot_digest(load_resources(snapshot_path))
            result["snapshot_matches_latest"] = digest == records[-1]["snapshot_sha256"]
    return result


def main():
    parser = argparse.ArgumentParser(description="Record and verify snapshot change history")
    subparsers = parser.add_subparsers(dest="command", required=True)
    append = subparsers.add_parser("append", help="record a reviewed snapshot")
    append.add_argument("snapshot", type=Path)
    append.add_argument("history", type=Path)
    append.add_argument("--note", required=True)
    verify = subparsers.add_parser("verify", help="check chain integrity")
    verify.add_argument("history", type=Path)
    verify.add_argument("snapshot", type=Path, nargs="?")
    args = parser.parse_args()
    if args.command == "append":
        record = append_record(args.history, args.snapshot, args.note)
        print(json.dumps({"appended": record}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(verify_history(args.history, args.snapshot),
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
