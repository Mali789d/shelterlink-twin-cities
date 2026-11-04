"""Record human re-verification of directory records; never fabricate it.

A record's ``verified_at`` asserts a person checked the provider's own source on
that date. This module is the only path that moves that date forward, and it
does so only when the operator explicitly names each record they re-checked.
It cannot move a date backward, touch sample records, or guess: an unchecked
record keeps its old date and goes stale on schedule.
"""
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .data import MAX_SNAPSHOT_BYTES, load_resources
from .freshness import Freshness, resource_freshness
from .models import Resource


def _aware(at: datetime) -> datetime:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("re-verification time must include a timezone")
    return at


def due_resources(resources: list[Resource], at: datetime,
                  within=None) -> list[dict]:
    """IDs and source URLs of records needing a fresh human check.

    A record is due once stale, or when it expires within ``within`` (a
    timedelta) so an operator can re-check before the export gate closes.
    Reports provenance pointers only, matching the audit's disclosure rules.
    """
    at = _aware(at)
    checked = [Resource.model_validate(item.model_dump()) for item in resources]
    due = []
    for item in checked:
        stale = resource_freshness(item, at) is not Freshness.CURRENT
        expiring = within is not None and not stale and (
            resource_freshness(item, at + within) is not Freshness.CURRENT)
        if stale or expiring:
            due.append({"id": item.id, "source_url": str(item.source_url),
                        "verified_at": item.verified_at.isoformat(),
                        "stale": stale})
    return due


def reverify(resources: list[Resource], checked_ids: set[str], at: datetime) -> list[Resource]:
    """Return copies with verified_at=at for exactly the re-checked records.

    Every checked id must exist; samples are never re-verifiable (replace them
    with real records instead); the new date must be aware, not in the future
    relative to nothing we can know, and never earlier than the record's
    current verified_at. Untouched records keep their own provenance.
    """
    at = _aware(at)
    if not checked_ids:
        raise ValueError("name each record that was re-checked; nothing is verified by default")
    checked = [Resource.model_validate(item.model_dump()) for item in resources]
    known = {item.id for item in checked}
    unknown = checked_ids - known
    if unknown:
        raise ValueError(f"cannot re-check unknown records: {sorted(unknown)}")
    updated = []
    for item in checked:
        if item.id not in checked_ids:
            updated.append(item)
            continue
        if item.is_sample:
            raise ValueError(f"sample record {item.id} is not verifiable; replace it with a real record")
        if at < item.verified_at:
            raise ValueError(f"re-verification of {item.id} would move verified_at backwards")
        updated.append(item.model_copy(update={"verified_at": at}))
    return updated


def reverify_file(path: Path, checked_ids: set[str], at: datetime) -> int:
    """Rewrite a snapshot in place with re-verified dates; atomic, bounded writes."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("refusing to rewrite a snapshot through a symlink")
    resources = load_resources(path)
    updated = reverify(resources, checked_ids, at)
    text = json.dumps([json.loads(item.model_dump_json()) for item in updated],
                      ensure_ascii=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot exceeds byte limit")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(checked_ids)


def main():
    parser = argparse.ArgumentParser(
        description="Record re-verification only for records checked against their source today")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--checked", action="append", default=[], metavar="ID",
                        help="record ID re-checked against its source_url; repeat per record")
    parser.add_argument("--due", action="store_true",
                        help="list records due for re-verification and exit")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    resources = load_resources(args.snapshot)
    if args.due:
        for item in due_resources(resources, now):
            print(f"{item['id']}\t{item['verified_at']}\t{item['source_url']}")
        return
    count = reverify_file(args.snapshot, set(args.checked), now)
    print(f"re-verified {count} record(s) at {now.isoformat()}")


if __name__ == "__main__":
    main()
