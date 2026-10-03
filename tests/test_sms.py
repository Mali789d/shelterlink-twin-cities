import pytest

from app.i18n import Language
from app.models import ResourceCategory
from app.sms import parse_sms, twiml


def test_parse_zip_and_category():
    query = parse_sms("Need a shelter near 55415")
    assert query is not None
    assert query.location == "55415"
    assert query.category == ResourceCategory.SHELTER


def test_parse_named_location():
    query = parse_sms("Saint Paul food")
    assert query is not None
    assert query.location == "saint paul"
    assert query.category == ResourceCategory.MEAL


def test_twiml_escapes_content():
    xml = twiml("Food & shelter <today>")
    assert "Food &amp; shelter &lt;today&gt;" in xml


def test_formatted_message_uses_safe_result_availability():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.data import load_resources
    from app.search import find_resources
    from app.sms import format_results

    observed = datetime(2026, 9, 23, 12, tzinfo=ZoneInfo("America/Chicago"))
    message = format_results(find_resources(load_resources(), 44.9778, -93.2650, at=observed))
    assert "availability unknown" in message
    assert "availability available" not in message
    assert ", open, " not in message
    assert "hours vary" in message



@pytest.mark.parametrize("term,category", [
    ("shelter", ResourceCategory.SHELTER), ("bed", ResourceCategory.SHELTER),
    ("refugio", ResourceCategory.SHELTER), ("hoy", ResourceCategory.SHELTER),
    ("meal", ResourceCategory.MEAL), ("food", ResourceCategory.MEAL),
    ("comida", ResourceCategory.MEAL), ("cunto", ResourceCategory.MEAL),
    ("warm", ResourceCategory.WARMING), ("warming", ResourceCategory.WARMING),
    ("centro de calor", ResourceCategory.WARMING), ("meel diirran", ResourceCategory.WARMING),
    ("shower", ResourceCategory.SHOWER), ("ducha", ResourceCategory.SHOWER),
    ("qubays", ResourceCategory.SHOWER),
])
def test_advertised_category_terms_work_for_zip_and_named_location(term, category):
    for location in ("55415", "Saint Paul"):
        query = parse_sms(f"{location} {term}")
        assert query.location == location.lower()
        assert query.category == category


@pytest.mark.parametrize("location", ["Bedford", "Warman", "Foodland", "Showerville"])
def test_category_substrings_in_place_names_do_not_select_service(location):
    query = parse_sms(location)
    assert query.location == location.lower()
    assert query.category is None


def test_longer_warming_word_removed_from_named_location():
    query = parse_sms("Saint Paul warming")
    assert query.location == "saint paul"
    assert query.category == ResourceCategory.WARMING


@pytest.mark.parametrize("body", ["55415 food shower", "Saint Paul hoy cunto", "55415 refugio ducha lang es"])
def test_multiple_distinct_services_require_clarification(body):
    assert parse_sms(body) is None


def test_synonyms_for_same_category_are_not_ambiguous():
    assert parse_sms("55415 shelter bed").category == ResourceCategory.SHELTER


def test_category_does_not_override_explicit_language():
    query = parse_sms("55415 hoy lang es")
    assert query.language == Language.SPANISH
    assert query.category == ResourceCategory.SHELTER
