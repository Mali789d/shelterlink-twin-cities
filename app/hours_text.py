"""Parse provider free-text weekly hours into the structured model format.

Provider exports (211, county, city) describe hours as text: "Mon-Fri 9 AM-5 PM".
Hand-converting each record invites mistakes, and a wrong parse would show wrong
hours to people in crisis, so this parser is strict: it converts a small set of
common, unambiguous formats and rejects everything else with a reason. Rejected
records stay out of the candidate snapshot for human review, and parsed output
is still only a candidate - review and publication remain separate steps.
"""
import re

DAY_NAMES = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

_EVERYDAY = re.compile(r"^(?:daily|every\s*day|7\s*days(?:\s*a\s*week)?)$", re.IGNORECASE)
_DAY = r"[A-Za-z]+"
_RANGE = re.compile(rf"^({_DAY})\s*(?:-|\u2013|\u2014|to)\s*({_DAY})$", re.IGNORECASE)
_TIME = re.compile(
    r"^(\d{1,2})(?::(\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?$", re.IGNORECASE)
_TIME_TOKEN = r"(?:\d{1,2}(?::\d{2})?\s*(?:a\.?\s?m\.?|p\.?\s?m\.?)?|noon|midnight)"
# One or more comma-separated ranges for the same days: real exports close
# and reopen within a day ("Mon 9 AM-12 PM, 1 PM-5 PM"), and the comma after a
# complete range can only mean another range - day names never follow one.
_TIME_RANGE = re.compile(
    rf"^({_TIME_TOKEN})\s*(?:-|\u2013|\u2014|\bto\b)\s*({_TIME_TOKEN})$",
    re.IGNORECASE)
_TIME_RANGE_SOURCE = rf"{_TIME_TOKEN}\s*(?:-|\u2013|\u2014|\bto\b)\s*{_TIME_TOKEN}"
_SEGMENT = re.compile(
    rf"^(?P<days>.+?)\s+(?P<times>{_TIME_RANGE_SOURCE}(?:\s*,\s*{_TIME_RANGE_SOURCE})*)$",
    re.IGNORECASE)


def _parse_time(text: str) -> str:
    """One clock time as HH:MM; 24:00 allowed only as an interval end (caller)."""
    text = text.strip().lower().replace(".", "").replace(" ", "")
    if text == "noon":
        return "12:00"
    if text == "midnight":
        raise ValueError("'midnight' is ambiguous (00:00 or 24:00); spell out the time")
    match = _TIME.match(text)
    if not match:
        raise ValueError(f"unrecognized time {text!r}")
    hour = int(match.group(1))
    minute = match.group(2)
    meridiem = match.group(3)
    if meridiem:
        if hour > 12:
            raise ValueError(f"time {text!r} mixes 24-hour and AM/PM formats")
        hour = hour % 12 + (12 if meridiem.startswith("p") else 0)
        minute = minute or "00"
    elif minute is None:
        # Bare "9" could be 9 AM or 09:00; refuse to guess.
        raise ValueError(
            f"ambiguous time {text!r}; use AM/PM or 24-hour time with minutes")
    if hour > 24 or int(minute) > 59 or (hour == 24 and minute != "00"):
        raise ValueError(f"invalid time {text!r}")
    return f"{hour:02d}:{minute}"


def _parse_days(text: str) -> list[int]:
    """Day names, comma lists, ascending ranges, or everyday shorthands."""
    text = text.strip()
    if _EVERYDAY.match(text):
        return list(range(7))
    range_match = _RANGE.match(text)
    if range_match:
        start_name, end_name = range_match.group(1).lower(), range_match.group(2).lower()
        if start_name not in DAY_NAMES or end_name not in DAY_NAMES:
            raise ValueError(f"unrecognized day range {text!r}")
        start, end = DAY_NAMES[start_name], DAY_NAMES[end_name]
        if start >= end:
            raise ValueError(
                f"day range {text!r} must run earlier to later in the week; "
                "list the days instead")
        return list(range(start, end + 1))
    days: list[int] = []
    for part in text.split(","):
        name = part.strip().lower()
        if name not in DAY_NAMES:
            raise ValueError(f"unrecognized day {part.strip()!r}")
        day = DAY_NAMES[name]
        if day in days:
            raise ValueError(f"day {part.strip()!r} listed twice")
        days.append(day)
    return sorted(days)


def parse_hours_text(text: str) -> dict[int, list[tuple[str, str]]]:
    """Strictly parse text like "Mon-Fri 9 AM-5 PM; Sat 10 AM-2 PM" into model hours.

    One segment may carry several comma-separated ranges for the same days
    ("Mon 9 AM-12 PM, 1 PM-5 PM") when a site closes and reopens within a day.

    Raises ValueError with a reason for anything ambiguous or unrecognized -
    the caller rejects the record for human review rather than guessing.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("hours text must be a non-empty string")
    normalized = " ".join(text.split())
    if re.fullmatch(r"(?:24\s*hours?|24\s*/\s*7|open\s*24\s*hours?)", normalized,
                    re.IGNORECASE):
        return {day: [("00:00", "24:00")] for day in range(7)}
    hours: dict[int, list[tuple[str, str]]] = {}
    for segment in normalized.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        time_match = _SEGMENT.match(segment)
        if not time_match:
            raise ValueError(
                f"segment {segment!r} must name days and a time range "
                "(expected e.g. Mon-Fri 9 AM-5 PM)")
        days_text = time_match.group("days").strip(" ,")
        if not days_text:
            raise ValueError(f"segment {segment!r} does not name its days")
        intervals = []
        for piece in time_match.group("times").split(","):
            range_match = _TIME_RANGE.match(piece.strip())
            if not range_match:
                raise ValueError(
                    f"segment {segment!r} has an unrecognized time range "
                    f"{piece.strip()!r} (expected e.g. 9 AM-12 PM)")
            start = _parse_time(range_match.group(1))
            end = _parse_time(range_match.group(2))
            if start == "24:00":
                raise ValueError("intervals cannot start at 24:00")
            if end != "24:00" and end <= start:
                raise ValueError(
                    f"interval {start}-{end} does not end after it starts; "
                    "split overnight hours by weekday")
            intervals.append((start, end))
        for day in _parse_days(days_text):
            hours.setdefault(day, []).extend(intervals)
    if not hours:
        raise ValueError("no day/time segments found")
    return {day: sorted(intervals) for day, intervals in sorted(hours.items())}
