"""Export digests pin the exact reviewed records, byte-identical with the web side."""
import json

import pytest

from app.export_directory import (_canonical_export_json, directory_snapshot,
                                  resources_digest)
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


def test_shared_vector_matches_the_web_reader():
    assert resources_digest(VECTOR) == VECTOR_DIGEST


def test_export_carries_the_digest_of_its_records():
    item = load_resources()[0].model_copy(update={"is_sample": False, "verified_at": NOW})
    snapshot = directory_snapshot([item], NOW)
    assert snapshot["resources_sha256"] == resources_digest(snapshot["resources"])
    assert isinstance(snapshot["resources_sha256"], str)
    assert len(snapshot["resources_sha256"]) == 64


def test_digest_covers_only_the_reviewed_field_set():
    # Injected claim fields change nothing the page may show, so they must not
    # change the digest either; the reader strips them at render time.
    injected = [dict(VECTOR[0], availability="available", open_now=True, hours={})]
    assert resources_digest(injected) == resources_digest([VECTOR[0]])


def test_digest_refuses_records_missing_a_reviewed_field():
    incomplete = [{key: value for key, value in VECTOR[0].items() if key != "phone"}]
    with pytest.raises(ValueError, match="reviewed field"):
        resources_digest(incomplete)


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
