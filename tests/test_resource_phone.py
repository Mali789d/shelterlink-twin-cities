"""Provider phone numbers go verbatim into SMS replies, so they must be dialable."""
from datetime import datetime, timezone

import pytest

from app.data import load_resources
from app.models import Resource


def resource(phone):
    return {
        "id": "fixture",
        "name": "Fixture Shelter",
        "category": "shelter",
        "address": "123 Main St",
        "latitude": 44.9753,
        "longitude": -93.2581,
        "phone": phone,
        "source_name": "Unit test fixture - not a live listing",
        "source_url": "https://example.org/source",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "is_sample": True,
    }


@pytest.mark.parametrize("phone", [
    "211",
    "911",
    "+1 (612) 555-0100",
    "(612) 555-0100",
    "612-555-0100",
    "612 555 0100",
    "+16125550100",
    "612-555-0100 x12",
    "612-555-0100 ext. 34",
])
def test_dialable_phone_numbers_pass(phone):
    assert Resource.model_validate(resource(phone)).phone == phone


def test_phone_remains_optional():
    assert Resource.model_validate(resource(None)).phone is None


@pytest.mark.parametrize("phone", [
    "",
    " ",
    "call me maybe",
    "612-555-O100",
    "12",
    "9" * 40,
    "911; call 555-0100",
    "555-0100 x1234567",
    "x211",
    "(612)",
    "+",
])
def test_prose_and_mistyped_phones_are_rejected(phone):
    with pytest.raises(ValueError):
        Resource.model_validate(resource(phone))


def test_injected_safety_text_cannot_hide_in_phone_field():
    with pytest.raises(ValueError):
        Resource.model_validate(resource("Emergency? Call 555-0100"))


def test_bundled_sample_fixture_phones_stay_valid():
    for item in load_resources():
        if item.phone is not None:
            Resource.model_validate(resource(item.phone))
