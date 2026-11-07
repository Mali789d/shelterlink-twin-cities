"""The verified directory seed: real records with traced provenance.

Every record in data/verified_resources.json was checked against the provider's
own website on its verified_at date. These tests freeze time at verification so
the pipeline's own gates (audit, export) judge the seed exactly as they would
have on the day it was checked; freshness expiry is covered by the existing
freshness tests. Nothing here asserts live availability.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.audit_directory import audit_resources
from app.data import load_resources
from app.export_directory import directory_snapshot
from app.ingest import within_service_area

SEED_PATH = Path(__file__).parent.parent / "data" / "verified_resources.json"


@pytest.fixture(scope="module")
def seed():
    return load_resources(SEED_PATH)


@pytest.fixture(scope="module")
def checked_at(seed):
    # Judge the seed one hour after its newest verification: inside the 24-hour
    # freshness window, independent of when the test suite happens to run.
    return max(item.verified_at for item in seed) + timedelta(hours=1)


def test_seed_is_real_and_complete(seed):
    assert len(seed) >= 4
    for item in seed:
        assert item.is_sample is False
        assert item.availability.value == "unknown"
        assert not item.hours  # no open-now claims from unverified schedules
        assert item.phone is not None
        assert item.source_url is not None and str(item.source_url).startswith("https://")
        assert item.verified_at.utcoffset() is not None
        assert within_service_area(item.latitude, item.longitude)


def test_bethel_hotel_record_matches_the_verified_source(seed):
    # Added 2026-11-07 against ugmtc.org: 435 University Ave E, Saint Paul;
    # men's programs line (651) 292-1721; intake 24/7. Hours stay empty per the
    # seed policy above: no open-now claims from unverified schedules.
    by_id = {item.id: item for item in seed}
    record = by_id["union-gospel-bethel-hotel"]
    assert record.name == "Bethel Hotel Men's Shelter"
    assert record.category.value == "shelter"
    assert record.address == "435 University Avenue East, Saint Paul, MN 55130"
    assert record.phone == "(651) 292-1721"
    assert not record.hours and record.availability.value == "unknown"
    assert str(record.source_url) == "https://www.ugmtc.org/programs/food-shelter/"
    assert str(record.website) == "https://www.ugmtc.org/"


def test_seed_covers_both_cities_and_multiple_categories(seed):
    cities = {item.address.rsplit(", ", 2)[1] for item in seed}
    assert cities == {"Minneapolis", "Saint Paul"}
    categories = {item.category.value for item in seed}
    assert {"shelter", "meal"} <= categories


def test_seed_passes_the_audit_gate_at_verification_time(seed, checked_at):
    report = audit_resources(seed, checked_at)
    assert report["export_validation_passes"] is True
    assert report["blockers"] == {
        "empty": False, "sample_ids": [], "stale_ids": [], "future_ids": [],
    }
    assert report["resource_count"] == len(seed)


def test_seed_exports_through_the_real_gate(seed, checked_at):
    snapshot = directory_snapshot(seed, checked_at)
    assert snapshot["schema_version"] == 1
    assert len(snapshot["resources"]) == len(seed)
    for record in snapshot["resources"]:
        # The export carries no availability, hours or open-now claims.
        assert set(record) == {
            "id", "name", "category", "address", "latitude", "longitude",
            "phone", "website", "source_name", "source_url", "verified_at",
        }
    encoded = json.dumps(snapshot).encode("utf-8")
    assert len(encoded) <= 1024 * 1024


def test_seed_expires_without_reverification(seed, checked_at):
    # Two days later the same records must fail the audit as stale: the pipeline
    # never keeps presenting old verification as current.
    report = audit_resources(seed, checked_at + timedelta(days=2))
    assert report["export_validation_passes"] is False
    assert sorted(report["blockers"]["stale_ids"]) == sorted(item.id for item in seed)
    with pytest.raises(ValueError, match="stale or future-dated"):
        directory_snapshot(seed, checked_at + timedelta(days=2))
