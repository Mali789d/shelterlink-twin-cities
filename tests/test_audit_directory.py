"""Audit is a read-only review aid, not a provenance or deployment grant."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from app.audit_directory import audit_resources
from app.data import load_resources
from app.export_directory import directory_snapshot
from app.history import append_record

AT = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def resource(identity="a", **changes):
    return load_resources()[0].model_copy(update={"id": identity, "is_sample": False,
                                                "verified_at": AT, **changes})


def test_all_blockers_reported_together_sorted_without_contact_data():
    data = [resource("z", is_sample=True, verified_at=AT + timedelta(seconds=1)),
            resource("b", verified_at=AT - timedelta(hours=24, seconds=1)),
            resource("a", is_sample=True)]
    report = audit_resources(data, AT)
    assert report["blockers"] == {"empty": False, "sample_ids": ["a", "z"],
                                  "stale_ids": ["b"], "future_ids": ["z"]}
    assert not report["export_validation_passes"]
    assert not report["provider_verification_confirmed"]
    assert "address" not in json.dumps(report)
    assert "phone" not in json.dumps(report)


@pytest.mark.parametrize("age,passes", [(0, True), (24 * 3600, True),
                                        (24 * 3600 + 1, False), (-1, False)])
def test_export_boundary_matches_real_exporter(age, passes):
    records = [resource(verified_at=AT - timedelta(seconds=age))]
    assert audit_resources(records, AT)["export_validation_passes"] is passes
    if passes:
        assert directory_snapshot(records, AT)["resources"]
    else:
        with pytest.raises(ValueError):
            directory_snapshot(records, AT)


def test_empty_is_blocked():
    assert audit_resources([], AT)["blockers"]["empty"]
    assert not audit_resources([], AT)["export_validation_passes"]


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        audit_resources([], AT.replace(tzinfo=None))


def test_duplicate_normalized_ids_and_bypassed_invalid_models_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        audit_resources([resource("a"), resource(" a ")], AT)
    with pytest.raises(ValueError):
        audit_resources([resource(latitude=91)], AT)


def test_timezone_offsets_compare_same_instants():
    other = AT.astimezone(timezone(timedelta(hours=-5)))
    assert audit_resources([resource(verified_at=other)], AT)["export_validation_passes"]


def test_audit_does_not_mutate_models():
    item = resource(is_sample=True)
    before = item.model_dump()
    audit_resources([item], AT)
    assert item.model_dump() == before


def test_cli_does_not_write_source_or_other_files(tmp_path):
    source = tmp_path / "resources.json"
    source.write_text(json.dumps([resource(is_sample=True).model_dump(mode="json")]))
    before = source.read_bytes()
    result = subprocess.run([sys.executable, "-m", "app.audit_directory", str(source)],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["blockers"]["sample_ids"] == ["a"]
    assert not report["provider_verification_confirmed"]
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]


def test_reachability_and_hours_warnings_sorted_ids_only():
    base = resource("full")
    data = [
        resource("z-walkin", phone=None, website=None),
        resource("b-nocontact-nohours", phone=None, website=None, hours={}),
        resource("a-nohours", hours={}),
        base,
    ]
    report = audit_resources(data, AT)
    assert report["warnings"] == {"walk_in_only_ids": ["b-nocontact-nohours", "z-walkin"],
                                  "no_hours_ids": ["a-nohours", "b-nocontact-nohours"],
                                  "out_of_area_ids": [], "expiring_soon_ids": []}
    # Warnings never gate export validation.
    assert report["export_validation_passes"]
    # Warning keys and values must not leak contact fields into the report.
    assert "address" not in json.dumps(report)
    assert "phone" not in json.dumps(report)
    assert "website" not in json.dumps(report)


def test_phone_or_website_alone_is_reachable_and_hours_present_is_no_warning():
    data = [resource("a", website=None),
            resource("b", phone=None, website="https://example.com/b"),
            resource("c", phone=None, website=None, hours={1: [("09:00", "17:00")]})]
    report = audit_resources(data, AT)
    assert report["warnings"] == {"walk_in_only_ids": ["c"], "no_hours_ids": [],
                                  "out_of_area_ids": [], "expiring_soon_ids": []}


def test_empty_directory_has_no_warnings():
    report = audit_resources([], AT)
    assert report["warnings"] == {"walk_in_only_ids": [], "no_hours_ids": [],
                                  "out_of_area_ids": [], "expiring_soon_ids": []}
    assert not report["export_validation_passes"]


def test_out_of_area_listings_warn_ids_only_without_gating():
    data = [resource("b-far", latitude=46.7867, longitude=-92.1005),
            resource("a-near"),
            resource("c-edge", latitude=45.30, longitude=-93.10)]
    report = audit_resources(data, AT)
    assert report["warnings"]["out_of_area_ids"] == ["b-far"]
    assert report["warnings"]["walk_in_only_ids"] == []
    assert report["export_validation_passes"]
    assert "address" not in json.dumps(report)


def test_every_covered_zip_centroid_passes_without_area_warning():
    from app.zip_centroids import TWIN_CITIES_ZIP_CENTROIDS
    data = [resource(f"zip-{code}", latitude=lat, longitude=lon)
            for code, (lat, lon) in TWIN_CITIES_ZIP_CENTROIDS.items()]
    report = audit_resources(data, AT)
    assert report["warnings"]["out_of_area_ids"] == []


def test_empty_directory_has_empty_area_warning():
    assert audit_resources([], AT)["warnings"] == {
        "walk_in_only_ids": [], "no_hours_ids": [], "out_of_area_ids": [],
        "expiring_soon_ids": []}


def _run_audit(tmp_path, records, *flags):
    source = tmp_path / 'resources.json'
    source.write_text(json.dumps([item.model_dump(mode='json') for item in records]))
    before = source.read_bytes()
    result = subprocess.run([sys.executable, '-m', 'app.audit_directory',
                             str(source), *flags], capture_output=True, text=True, timeout=10)
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]
    return result


@pytest.mark.parametrize('case', ['empty', 'sample', 'stale', 'future', 'combined'])
def test_check_cli_fails_for_each_export_blocker_with_complete_json(tmp_path, case):
    now = datetime.now(timezone.utc)
    cases = {
        'empty': [],
        'sample': [resource(is_sample=True, verified_at=now)],
        'stale': [resource(verified_at=now - timedelta(hours=25))],
        'future': [resource(verified_at=now + timedelta(hours=1))],
        'combined': [resource('sample', is_sample=True, verified_at=now),
                     resource('stale', verified_at=now - timedelta(hours=25)),
                     resource('future', verified_at=now + timedelta(hours=1))],
    }
    result = _run_audit(tmp_path, cases[case], '--check')
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report['export_validation_passes'] is False
    assert report['provider_verification_confirmed'] is False
    assert not result.stderr
    assert report['blockers']['empty'] == (case == 'empty')
    if case == 'combined':
        assert report['blockers'] == {'empty': False, 'sample_ids': ['sample'],
                                      'stale_ids': ['stale'], 'future_ids': ['future']}
    for private in ('address', 'phone', 'website', '612'):
        assert private not in result.stdout


@pytest.mark.parametrize('warnings_only', [False, True])
def test_check_cli_succeeds_for_valid_data_even_with_advisory_warnings(tmp_path, warnings_only):
    changes = {'verified_at': datetime.now(timezone.utc)}
    if warnings_only:
        # Three hours from the freshness deadline, so every advisory warning fires.
        changes.update(phone=None, website=None, hours={}, latitude=46.7867,
                       longitude=-92.1005,
                       verified_at=datetime.now(timezone.utc) - timedelta(hours=21))
    result = _run_audit(tmp_path, [resource(**changes)], '--check')
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['export_validation_passes'] is True
    assert report['provider_verification_confirmed'] is False
    if warnings_only:
        assert all(report['warnings'].values())
    assert not result.stderr


def test_report_only_cli_preserves_success_exit_for_blocked_data(tmp_path):
    result = _run_audit(tmp_path, [resource(is_sample=True)])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['export_validation_passes'] is False


def test_check_cli_malformed_data_fails_without_success_report_or_writes(tmp_path):
    source = tmp_path / 'resources.json'
    source.write_text('[{"id": "missing-fields"}]')
    before = source.read_bytes()
    result = subprocess.run([sys.executable, '-m', 'app.audit_directory', str(source), '--check'],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not result.stdout
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("seconds_until_deadline,expected", [
    (6 * 3600 + 1, False), (6 * 3600, True), (3600, True), (0, True), (-1, False)])
def test_expiring_soon_warning_tracks_the_freshness_deadline(seconds_until_deadline, expected):
    verified = AT - timedelta(hours=24) + timedelta(seconds=seconds_until_deadline)
    report = audit_resources([resource(verified_at=verified)], AT)
    assert (report["warnings"]["expiring_soon_ids"] == ["a"]) is expected
    if seconds_until_deadline >= 0:
        # Advance notice never gates: the record is still current at the deadline.
        assert report["export_validation_passes"] is True
        assert report["blockers"]["stale_ids"] == []
    else:
        # Past the deadline the blocker, not the warning, says what happened.
        assert report["blockers"]["stale_ids"] == ["a"]


def test_future_dated_records_warn_as_blockers_not_expiring_soon():
    report = audit_resources([resource(verified_at=AT + timedelta(hours=1))], AT)
    assert report["blockers"]["future_ids"] == ["a"]
    assert report["warnings"]["expiring_soon_ids"] == []


def test_expiring_soon_ids_sorted_without_contact_data():
    soon = AT - timedelta(hours=20)  # freshness deadline four hours away
    report = audit_resources([resource("z", verified_at=soon),
                              resource("b", verified_at=soon),
                              resource("fresh")], AT)
    assert report["warnings"]["expiring_soon_ids"] == ["b", "z"]
    assert report["export_validation_passes"] is True
    for private in ("phone", "website", "address"):
        assert private not in json.dumps(report)


def test_report_states_the_expiring_soon_window():
    assert audit_resources([], AT)["expiring_soon_window_seconds"] == 6 * 3600


def _write_source(tmp_path, records):
    source = tmp_path / 'resources.json'
    source.write_text(json.dumps([item.model_dump(mode='json') for item in records]))
    return source


def _append(history_path, source, note, at):
    append_record(history_path, source, note, at=at)


def _run_audit_history(tmp_path, *flags):
    source = tmp_path / 'resources.json'
    history = tmp_path / 'history.jsonl'
    before_source = source.read_bytes()
    before_history = history.read_bytes() if history.exists() else None
    result = subprocess.run([sys.executable, '-m', 'app.audit_directory',
                             str(source), *flags], capture_output=True, text=True, timeout=10)
    # The audit is read-only even when it verifies history.
    assert source.read_bytes() == before_source
    if before_history is None:
        assert not history.exists()
    else:
        assert history.read_bytes() == before_history
    expected = {source, history} if history.exists() else {source}
    assert set(tmp_path.iterdir()) == expected
    return result


def test_history_gate_passes_when_chain_and_anchor_match(tmp_path):
    source = _write_source(tmp_path, [resource(verified_at=datetime.now(timezone.utc))])
    history = tmp_path / 'history.jsonl'
    _append(history, source, 'initial review', at=AT)
    result = _run_audit_history(tmp_path, '--history', str(history), '--check')
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['history'] == {'record_count': 1, 'chain_ok': True,
                                 'snapshot_matches_latest': True, 'problems': []}
    assert report['export_validation_passes'] is True
    assert not result.stderr


def test_history_gate_fails_when_an_earlier_record_is_rewritten(tmp_path):
    first = _write_source(tmp_path, [resource('one', verified_at=datetime.now(timezone.utc))])
    history = tmp_path / 'history.jsonl'
    _append(history, first, 'first review', at=AT)
    _write_source(tmp_path, [resource('two', verified_at=datetime.now(timezone.utc))])
    _append(history, tmp_path / 'resources.json', 'second review',
            at=AT + timedelta(minutes=1))
    lines = history.read_text().splitlines()
    rewritten = json.loads(lines[0])
    rewritten['note'] = 'quietly altered after the fact'
    lines[0] = json.dumps(rewritten)
    history.write_text('\n'.join(lines) + '\n')
    result = _run_audit_history(tmp_path, '--history', str(history), '--check')
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report['history']['chain_ok'] is False
    assert report['history']['snapshot_matches_latest'] is True
    assert any('line 2' in problem for problem in report['history']['problems'])
    for private in ('quietly altered', 'second review'):
        assert private not in json.dumps(report['history']['problems'])


def test_history_gate_fails_when_the_snapshot_changed_without_a_record(tmp_path):
    source = _write_source(tmp_path, [resource('kept', verified_at=datetime.now(timezone.utc))])
    history = tmp_path / 'history.jsonl'
    _append(history, source, 'reviewed state', at=AT)
    # A later hand edit that skips its history record must not pass the gate.
    _write_source(tmp_path, [resource('swapped', verified_at=datetime.now(timezone.utc))])
    result = _run_audit_history(tmp_path, '--history', str(history), '--check')
    assert result.returncode == 1
    report = json.loads(result.stdout)
    # The chain itself is intact; the anchor to the audited snapshot is not.
    assert report['history']['chain_ok'] is True
    assert report['history']['snapshot_matches_latest'] is False


def test_history_gate_fails_when_the_log_is_missing(tmp_path):
    _write_source(tmp_path, [resource(verified_at=datetime.now(timezone.utc))])
    result = _run_audit_history(tmp_path, '--history',
                                str(tmp_path / 'history.jsonl'), '--check')
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report['history']['record_count'] == 0
    assert report['history']['chain_ok'] is False
    assert 'history is empty' in report['history']['problems']


def test_history_report_only_keeps_success_exit_for_a_broken_chain(tmp_path):
    source = _write_source(tmp_path, [resource(verified_at=datetime.now(timezone.utc))])
    history = tmp_path / 'history.jsonl'
    _append(history, source, 'reviewed state', at=AT)
    _write_source(tmp_path, [resource('drifted', verified_at=datetime.now(timezone.utc))])
    result = _run_audit_history(tmp_path, '--history', str(history))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['history']['snapshot_matches_latest'] is False


def test_history_gate_still_fails_on_export_blockers_with_a_clean_chain(tmp_path):
    source = _write_source(tmp_path, [resource(is_sample=True)])
    history = tmp_path / 'history.jsonl'
    _append(history, source, 'recorded sample snapshot', at=AT)
    result = _run_audit_history(tmp_path, '--history', str(history), '--check')
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report['export_validation_passes'] is False
    assert report['history']['chain_ok'] is True
    assert report['history']['snapshot_matches_latest'] is True


def test_audit_without_history_flag_reports_no_history_section(tmp_path):
    result = _run_audit(tmp_path, [resource(verified_at=datetime.now(timezone.utc))], '--check')
    assert result.returncode == 0, result.stderr
    assert 'history' not in json.loads(result.stdout)
