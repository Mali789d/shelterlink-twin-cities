"""Replies must stay under the provider's 1,600-character ceiling without losing safety text."""
from datetime import datetime, timezone

import pytest

from app.i18n import AVAILABILITY, MESSAGES, Language
from app.models import Availability, Resource, ResourceCategory, ResourceResult
from app.sms import MAX_MESSAGE_CHARS, format_results


def make_result(result_id: str, name: str, address: str, distance: float = 1.0) -> ResourceResult:
    resource = Resource(
        id=result_id,
        name=name,
        category=ResourceCategory.SHELTER,
        address=address,
        latitude=44.9753,
        longitude=-93.2581,
        phone="6125550100",
        source_name="Unit test fixture - not a live listing",
        source_url="https://example.org/source",
        verified_at=datetime(2026, 10, 17, 12, tzinfo=timezone.utc),
        is_sample=True,
    )
    return ResourceResult(
        resource=resource,
        distance_miles=distance,
        open_now=False,
        availability=Availability.UNKNOWN,
        data_freshness="stale",
    )


def expected_line(result: ResourceResult, language: Language = Language.ENGLISH) -> str:
    messages = MESSAGES[language]
    status = messages["open"] if result.open_now else messages["hours_vary"]
    availability = AVAILABILITY[language][result.availability.value]
    phone = f" {result.resource.phone}" if result.resource.phone else ""
    return (
        f"{result.resource.name} - {result.distance_miles} mi, {status}, "
        f"{messages['availability']} {availability}. {result.resource.address}.{phone}"
    )


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("kind", ["help", "opt_in", "unknown_location", "none", "not_live"])
def test_every_static_reply_fits_provider_limit(language, kind):
    assert len(MESSAGES[language][kind]) <= MAX_MESSAGE_CHARS


def test_short_results_are_unchanged():
    results = [make_result("a", "Mary's Place", "123 Main St", 0.4),
               make_result("b", "Union Gospel Mission", "456 Cedar Ave", 1.2)]
    message = format_results(results)
    expected = "\n".join([MESSAGES[Language.ENGLISH]["heading"],
                          *(expected_line(item) for item in results),
                          MESSAGES[Language.ENGLISH]["footer"]])
    assert message == expected
    assert "\u2026" not in message
    assert len(message) <= MAX_MESSAGE_CHARS


@pytest.mark.parametrize("language", list(Language))
def test_overflow_drops_farther_results_and_keeps_footer(language):
    name = "Harbor Light Center For Families And Children Emergency Shelter " * 8
    address = "1234 Very Long Street Name Northeast Suite 500 " * 8
    results = [make_result("near", name, address, 0.4),
               make_result("mid", name, address, 1.2),
               make_result("far", name, address, 2.8)]
    message = format_results(results, language)
    assert len(message) <= MAX_MESSAGE_CHARS
    assert message.startswith(MESSAGES[language]["heading"])
    assert message.endswith(MESSAGES[language]["footer"])
    assert "211" in message and "911" in message
    # Nearest-first order is preserved: the farther results never displace the nearest.
    assert "2.8 mi" not in message


def test_exact_limit_reply_is_not_truncated():
    base = format_results([make_result("a", "Base", "1 Main St", 0.4)])
    padding = MAX_MESSAGE_CHARS - len(base)
    name = "Base" + "x" * padding
    message = format_results([make_result("a", name, "1 Main St", 0.4)])
    assert len(message) == MAX_MESSAGE_CHARS
    assert "\u2026" not in message
    assert name in message


def test_one_character_over_limit_truncates_display_line():
    base = format_results([make_result("a", "Base", "1 Main St", 0.4)])
    padding = MAX_MESSAGE_CHARS - len(base) + 1
    name = "Base " + "x" * padding
    message = format_results([make_result("a", name, "1 Main St", 0.4)])
    assert len(message) <= MAX_MESSAGE_CHARS
    assert "\u2026" in message
    assert message.endswith(MESSAGES[Language.ENGLISH]["footer"])
    truncated_line = message.split("\n")[1]
    assert truncated_line.endswith("\u2026")
    # Truncation shortens a copy of the line; it never invents replacement text.
    original_line = expected_line(make_result("a", name, "1 Main St", 0.4))
    assert original_line.startswith(truncated_line[:-1])


def test_mixed_lengths_keep_whole_nearby_lines():
    results = [make_result("near", "Mary's Place", "123 Main St", 0.4),
               make_result("far", "Overflow Shelter " * 60, "456 Cedar Ave " * 40, 1.2)]
    message = format_results(results)
    assert len(message) <= MAX_MESSAGE_CHARS
    assert "Mary's Place - 0.4 mi" in message
    assert "\u2026" in message
    assert message.endswith(MESSAGES[Language.ENGLISH]["footer"])
