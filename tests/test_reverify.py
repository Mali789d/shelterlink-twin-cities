"""Re-verification records a human check; it can never fabricate one."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.audit_directory import audit_resources
from app.data import load_resources
from app.models import Resource
from app.reverify import due_resources, reverify, reverify_file

AT = datetime(2026, 11, 3, 21, 0, tzinfo=timezone.utc)
LATER = AT + timedelta(hours=2)


def _record(rid, verified_at=AT, is_sample=False):
    return Resource.model_validate({
        "id": rid, "name": f"Site {rid}", "category": "shelter",
        "address": "1 Main St, Minneapolis, MN 55401",
        "latitude": 44.98, "longitude": -93.27, "phone": "(612) 555-0100",
        "source_name": "Provider", "source_url": f"https://example.org/{rid}",
        "verified_at": verified_at.isoformat(), "is_sample": is_sample,
    })


def test_due_lists_stale_and_expiring_only():
    fresh = _record("fresh", AT)
    old = _record("old", AT - timedelta(days=3))
    due = due_resources([fresh, old], AT)
    assert [item["id"] for item in due] == ["old"]
    assert due[0]["stale"] is True
    # Expiring soon shows up when a horizon is given, flagged not-yet-stale.
    due = due_resources([fresh], AT + timedelta(hours=23), within=timedelta(hours=2))
    assert [item["id"] for item in due] == ["fresh"]
    assert due[0]["stale"] is False


def test_due_requires_aware_time():
    with pytest.raises(ValueError, match="timezone"):
        due_resources([_record("a")], datetime(2026, 11, 3, 21, 0))


def test_reverify_requires_explicit_records():
    with pytest.raises(ValueError, match="re-checked"):
        reverify([_record("a")], set(), AT)


def test_reverify_rejects_unknown_ids():
    with pytest.raises(ValueError, match="unknown records.*ghost"):
        reverify([_record("a")], {"a", "ghost"}, AT)


def test_reverify_rejects_samples():
    with pytest.raises(ValueError, match="sample record"):
        reverify([_record("s", is_sample=True)], {"s"}, AT)


def test_reverify_never_moves_dates_backwards():
    with pytest.raises(ValueError, match="backwards"):
        reverify([_record("a", AT)], {"a"}, AT - timedelta(seconds=1))


def test_reverify_updates_only_checked_records():
    keep = _record("keep", AT)
    bump = _record("bump", AT)
    updated = reverify([keep, bump], {"bump"}, LATER)
    by_id = {item.id: item for item in updated}
    assert by_id["keep"].verified_at == AT
    assert by_id["bump"].verified_at == LATER
    # Everything but the date is preserved, and the result revalidates.
    assert by_id["bump"].phone == bump.phone
    assert by_id["bump"].source_url == bump.source_url
    assert audit_resources(updated, LATER)["export_validation_passes"] is True


def test_reverify_file_round_trips_and_refuses_symlink(tmp_path):
    path = tmp_path / "resources.json"
    path.write_text(json.dumps([
        json.loads(_record("one", AT).model_dump_json()),
        json.loads(_record("two", AT).model_dump_json()),
    ]))
    count = reverify_file(path, {"one"}, LATER)
    assert count == 1
    loaded = {item.id: item for item in load_resources(path)}
    assert loaded["one"].verified_at == LATER
    assert loaded["two"].verified_at == AT

    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="symlink"):
        reverify_file(link, {"one"}, LATER + timedelta(hours=1))
    # The failed call left the file exactly as the successful one wrote it.
    assert {item.id: item.verified_at for item in load_resources(path)} == {
        "one": LATER, "two": AT}
