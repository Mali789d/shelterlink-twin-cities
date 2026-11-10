"""Export digests pin the exact reviewed envelope, byte-identical with the web side."""
import json

import pytest

from app.export_directory import (_canonical_export_json, directory_snapshot,
                                  export_digest, resources_digest)
from app.data import load_resources
from datetime import datetime, timezone

NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)

# Shared with tests/test_export_integrity.mjs: same records, same expected
# digest. Covers non-ASCII text, integral and fractional coordinates, a null
# phone and a null website. If either side's canonical form drifts, one of
# the two suites fails on this literal.
VECTOR = [{"address": "123 Cañon Avenue, Suite 5", "category": "shelter",
           "id": "vector-b", "latitude": 45.0, "longitude": -93.265,
           "name": "St. Mary’s Place – “Open Door”", "phone": "211",
           "source_name": "Provider – reviewed",
           "source_url": "https://example.com/b",
           "verified_at": "2026-11-10T12:00:00Z", "website": None},
          {"address": "1 Main St", "category": "meal", "id": "vector-a",
           "latitude": 44.9778, "longitude": -93.0, "name": "Vector A",
           "phone": None, "source_name": "Provider",
           "source_url": "https://example.com/a",
           "verified_at": "2026-11-10T11:00:00Z", "website": "https://example.com"}]
VECTOR_DIGEST = "d2b3369e2650c24f277099653f4e77f4e5d2123f035ff1b04fb1127016996fda"

# The envelope the page consults when deciding whether and what to render.
ENVELOPE = {"generated_at": "2026-11-10T12:00:00Z", "resources": VECTOR,
            "schema_version": 1}
ENVELOPE_DIGEST = "4bea782f609d293c003956d5c80e5b3fbdd00550108520f450afb61c2647728d"


def test_shared_record_vector_matches_the_web_reader():
    assert resources_digest(VECTOR) == VECTOR_DIGEST


def test_shared_envelope_vector_matches_the_web_reader():
    assert export_digest(ENVELOPE) == ENVELOPE_DIGEST


def test_export_carries_the_digest_of_its_envelope():
    item = load_resources()[0].model_copy(update={"is_sample": False, "verified_at": NOW})
    snapshot = directory_snapshot([item], NOW)
    assert snapshot["export_sha256"] == export_digest(snapshot)
    assert "resources_sha256" not in snapshot
    assert isinstance(snapshot["export_sha256"], str)
    assert len(snapshot["export_sha256"]) == 64


def test_envelope_digest_covers_generated_at():
    # A stale export rolled forward must fail integrity, not just freshness.
    rolled = dict(ENVELOPE, generated_at="2026-11-10T12:30:00Z")
    assert export_digest(rolled) != ENVELOPE_DIGEST


def test_envelope_digest_covers_schema_version():
    moved = dict(ENVELOPE, schema_version=2)
    assert export_digest(moved) != ENVELOPE_DIGEST


def test_envelope_digest_covers_every_record_field():
    edited = json.loads(json.dumps(ENVELOPE))
    edited["resources"][0]["name"] = "Edited after export"
    assert export_digest(edited) != ENVELOPE_DIGEST


def test_digest_covers_only_the_reviewed_field_set():
    # Injected claim fields change nothing the page may show, so they must not
    # change the digest either; the reader strips them at render time.
    injected_records = [dict(VECTOR[0], availability="available", open_now=True, hours={})]
    assert resources_digest(injected_records) == resources_digest([VECTOR[0]])
    injected = dict(ENVELOPE, notice="Forged notice", resources=injected_records + [VECTOR[1]])
    assert export_digest(injected) == ENVELOPE_DIGEST


def test_digest_refuses_records_missing_a_reviewed_field():
    incomplete = [{key: value for key, value in VECTOR[0].items() if key != "phone"}]
    with pytest.raises(ValueError, match="reviewed field"):
        resources_digest(incomplete)
    with pytest.raises(ValueError, match="reviewed field"):
        export_digest(dict(ENVELOPE, resources=incomplete))


def test_digest_refuses_an_envelope_missing_a_reviewed_field():
    for key in ("generated_at", "resources", "schema_version"):
        with pytest.raises(ValueError, match="envelope field"):
            export_digest({k: v for k, v in ENVELOPE.items() if k != key})


def test_canonical_form_matches_javascript_number_and_string_rules():
    # Integral floats render as integers (JavaScript has one number type);
    # strings keep UTF-8 without ASCII escaping; object keys sort.
    assert _canonical_export_json({"b": 45.0, "a": "Cañon"}) == '{"a":"Cañon","b":45}'
    assert _canonical_export_json([True, None, -93.265]) == '[true,null,-93.265]'
    with pytest.raises(ValueError, match="non-finite"):
        _canonical_export_json(float("inf"))


def test_digest_is_order_sensitive_and_deterministic():
    assert resources_digest(VECTOR) == resources_digest(json.loads(json.dumps(VECTOR)))
    assert resources_digest(list(reversed(VECTOR))) != VECTOR_DIGEST
    assert export_digest(ENVELOPE) == export_digest(json.loads(json.dumps(ENVELOPE)))
