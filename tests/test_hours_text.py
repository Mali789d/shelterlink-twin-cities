"""Provider free-text hours parse strictly or reject the record for review.

Real 211/county exports describe hours as text ("Mon-Fri 9 AM-5 PM"). The
parser converts common unambiguous formats into structured model hours and
refuses everything else - a guessed schedule is worse than a rejected record,
because review and publication stay separate from ingestion.
"""
import pytest
from pydantic import ValidationError

from app.hours_text import parse_hours_text
from app.ingest import ingest_records
from app.models import Resource
from tests.test_ingest import MAPPING, provider_record


def test_weekday_range_with_meridiem():
    assert parse_hours_text("Mon-Fri 9 AM-5 PM") == {
        day: [("09:00", "17:00")] for day in range(5)}


def test_multiple_segments_and_minutes():
    assert parse_hours_text("Mon-Fri 9 AM-5 PM; Sat 10:00 AM-2 PM") == {
        **{day: [("09:00", "17:00")] for day in range(5)},
        5: [("10:00", "14:00")]}


def test_day_list_and_noon():
    assert parse_hours_text("Mon, Wed, Fri noon to 4 PM") == {
        0: [("12:00", "16:00")], 2: [("12:00", "16:00")], 4: [("12:00", "16:00")]}


def test_everyday_shorthands_and_24_hour_times():
    expected = {day: [("08:00", "20:00")] for day in range(7)}
    assert parse_hours_text("Daily 08:00-20:00") == expected
    assert parse_hours_text("every day 08:00 to 20:00") == expected
    assert parse_hours_text("7 days a week 08:00-20:00") == expected


def test_all_day_formats():
    expected = {day: [("00:00", "24:00")] for day in range(7)}
    assert parse_hours_text("24 hours") == expected
    assert parse_hours_text("24/7") == expected
    assert parse_hours_text("Open 24 Hours") == expected


def test_en_dash_dotted_meridiem_and_extra_whitespace():
    assert parse_hours_text("Monday\u2013Friday   9:30 a.m. - 5:00 p.m.") == {
        day: [("09:30", "17:00")] for day in range(5)}


def test_parsed_output_passes_model_validation():
    resource_hours = parse_hours_text("Tue-Thu 1 PM-6:30 PM")
    record = provider_record(HoursText="ignored")
    mapped = {target: record[source] for target, source in MAPPING.items() if source in record}
    mapped["hours"] = resource_hours
    Resource.model_validate(mapped)  # must not raise


@pytest.mark.parametrize("text", [
    "call for hours",
    "by appointment only",
    "Mon-Fri 9-5",                    # bare numbers are ambiguous
    "Sat-Sun 9 PM-2 AM",              # overnight must be split by weekday
    "Fri-Mon 9 AM-5 PM",              # wrap-around range is ambiguous
    "9 AM-5 PM",                      # no days named
    "Mon 17:00 PM-19:00",             # mixed 24-hour and meridiem
    "Mon 9 AM-9 AM",                  # zero-length interval
    "Mon 25:00-26:00",                # impossible time
    "Mon, Mon 9 AM-5 PM",             # duplicate day
    "Mon-Fri 9 AM-midnight",          # ambiguous boundary
    "Mon 24:00-24:00",                # interval cannot start at 24:00
    "",
    "   ",
])
def test_ambiguous_or_unrecognized_text_is_rejected(text):
    with pytest.raises(ValueError):
        parse_hours_text(text)


def test_overlapping_intervals_fail_model_validation():
    hours = parse_hours_text("Mon 9 AM-1 PM; Mon 12 PM-5 PM")
    record = provider_record()
    mapped = {target: record[source] for target, source in MAPPING.items() if source in record}
    mapped["hours"] = hours
    with pytest.raises(ValidationError):
        Resource.model_validate(mapped)


def _ingest_with_hours(hours_value):
    mapping = dict(MAPPING, hours="HoursText")
    return ingest_records([provider_record(HoursText=hours_value)], mapping)


def test_ingest_parses_string_hours_into_the_candidate():
    report = _ingest_with_hours("Mon-Fri 8 AM-8 PM")
    assert not report["rejections"]
    (resource,) = report["candidates"]
    assert resource.hours == {day: [("08:00", "20:00")] for day in range(5)}


def test_ingest_rejects_unparseable_hours_and_keeps_the_reason():
    report = _ingest_with_hours("call for hours")
    assert not report["candidates"]
    (rejection,) = report["rejections"]
    assert rejection["record_id"] == "hc-101"
    (error,) = rejection["errors"]
    assert error.startswith("hours: segment 'call for hours'")


def test_ingest_leaves_structured_hours_untouched():
    structured = {1: [("10:00", "12:00")]}
    report = _ingest_with_hours(structured)
    assert not report["rejections"]
    assert report["candidates"][0].hours == structured
