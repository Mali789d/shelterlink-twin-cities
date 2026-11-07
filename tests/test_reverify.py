"""Re-verification records a human check; it can never fabricate one."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.audit_directory import audit_resources
from app.data import load_resources
from app.models import Resource
from app.reverify import due_resources, main, reverify, reverify_file

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


def test_due_marks_samples_for_replacement():
    # reverify refuses sample records: the queue must flag which due records
    # need replacement so --due output can never become a failing --checked run.
    old_sample = _record("old-sample", AT - timedelta(days=3), is_sample=True)
    old_real = _record("old-real", AT - timedelta(days=3))
    due = {item["id"]: item for item in due_resources([old_sample, old_real], AT)}
    assert due["old-sample"]["sample"] is True
    assert due["old-real"]["sample"] is False


def test_due_cli_names_the_action_per_record(tmp_path, capsys, monkeypatch):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps([
        json.loads(_record("old-real", AT - timedelta(days=3)).model_dump_json()),
        json.loads(_record("old-sample", AT - timedelta(days=3),
                         is_sample=True).model_dump_json()),
    ]), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["reverify", str(snapshot), "--due"])
    main()
    lines = capsys.readouterr().out.strip().splitlines()
    actions = {line.split("\t")[0]: line.split("\t")[3] for line in lines}
    assert actions == {"old-real": "reverify", "old-sample": "replace"}


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


@pytest.mark.parametrize("within", [-1, 2.5, "2", timedelta(seconds=-1), timedelta(days=8)])
def test_due_refuses_invalid_horizons(within):
    with pytest.raises(ValueError, match="horizon"):
        due_resources([_record("a")], AT, within=within)


@pytest.mark.parametrize("operation", ["due", "reverify"])
def test_direct_calls_refuse_duplicate_ids(operation):
    records = [_record("same"), _record("same", AT - timedelta(days=1))]
    with pytest.raises(ValueError, match="duplicate resource IDs"):
        if operation == "due":
            due_resources(records, LATER)
        else:
            reverify(records, {"same"}, LATER)


@pytest.mark.parametrize("hour, expected", [(24, []), (25, ["a"])])
def test_due_horizon_obeys_exact_freshness_boundary(hour, expected):
    assert [row["id"] for row in due_resources(
        [_record("a")], AT, within=timedelta(hours=hour))] == expected


def test_due_horizon_uses_elapsed_time_across_fall_back():
    from zoneinfo import ZoneInfo
    zone = ZoneInfo("America/Chicago")
    # At 00:30 CDT, two elapsed hours end at 01:30 CST, not 02:30 CST.
    # This record will then be 23h45m old, still current. Wall-clock addition
    # incorrectly makes it 24h45m old and queues it early.
    checked = datetime(2026, 10, 31, 7, 45, tzinfo=timezone.utc)
    local_now = datetime(2026, 11, 1, 0, 30, tzinfo=zone)
    assert due_resources([_record("a", checked)], local_now,
                         within=timedelta(hours=2)) == []


def test_due_horizon_uses_elapsed_time_across_spring_forward():
    from zoneinfo import ZoneInfo
    zone = ZoneInfo("America/Chicago")
    # Two elapsed hours from 01:30 CST end at 04:30 CDT. Wall-clock
    # addition ends at 03:30 CDT, an hour short of the intended horizon.
    checked = datetime(2026, 3, 7, 8, 45, tzinfo=timezone.utc)
    local_now = datetime(2026, 3, 8, 1, 30, tzinfo=zone)
    assert [row["id"] for row in due_resources([_record("a", checked)],
            local_now, within=timedelta(hours=2))] == ["a"]


def _cli(tmp_path, *args):
    import subprocess
    import sys
    path = tmp_path / "snapshot.json"
    # Current at run time, but will expire well inside the requested 48h.
    now = datetime.now(timezone.utc)
    path.write_text(json.dumps([json.loads(_record("a", now).model_dump_json())]))
    before = path.read_bytes()
    process = subprocess.run([sys.executable, "-m", "app.reverify", str(path), *args],
                             capture_output=True, text=True)
    assert path.read_bytes() == before
    return process


def test_cli_can_list_expiring_records_without_modifying_dates(tmp_path):
    process = _cli(tmp_path, "--due", "--within-hours", "48")
    assert process.returncode == 0
    assert "a\t" in process.stdout
    assert "https://example.org/a" in process.stdout


@pytest.mark.parametrize("args", [
    ["--within-hours", "2"], ["--due", "--checked", "a"],
    ["--due", "--within-hours", "-1"], ["--due", "--within-hours", "169"],
    ["--due", "--within-hours", "1.5"], ["--due", "--within-hours", "nan"],
])
def test_cli_rejects_invalid_or_conflicting_modes_without_writing(tmp_path, args):
    process = _cli(tmp_path, *args)
    assert process.returncode == 2
    assert "error:" in process.stderr
