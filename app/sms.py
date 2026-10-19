import re
from dataclasses import dataclass
from html import escape

from .i18n import AVAILABILITY, MESSAGES, Language, parse_language, strip_language_directive
from .models import ResourceCategory, ResourceResult

# Match complete words/phrases, never substrings in location names (Bedford, Warman).
# These terms mirror the vocabulary already advertised in the language HELP replies.
CATEGORY_WORDS = {
    "shelter": ResourceCategory.SHELTER,
    "bed": ResourceCategory.SHELTER,
    "refugio": ResourceCategory.SHELTER,
    "hoy": ResourceCategory.SHELTER,
    "meal": ResourceCategory.MEAL,
    "food": ResourceCategory.MEAL,
    "comida": ResourceCategory.MEAL,
    "cunto": ResourceCategory.MEAL,
    "warm": ResourceCategory.WARMING,
    "warming": ResourceCategory.WARMING,
    "centro de calor": ResourceCategory.WARMING,
    "meel diirran": ResourceCategory.WARMING,
    "shower": ResourceCategory.SHOWER,
    "ducha": ResourceCategory.SHOWER,
    "qubays": ResourceCategory.SHOWER,
}
CATEGORY_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(word) for word in sorted(CATEGORY_WORDS, key=len, reverse=True)) + r")\b"
)


@dataclass(frozen=True)
class SmsQuery:
    location: str
    category: ResourceCategory | None
    language: Language = Language.ENGLISH


# Natural phrasing puts one of these before the place ("shelter in Minneapolis").
# Dropping a single leading preposition is safe: no Twin Cities place name starts
# with one, and a message that is only a preposition still yields no location.
LEADING_PREPOSITIONS = ("in", "near", "around", "at", "by")


def _drop_leading_preposition(location: str) -> str:
    first, separator, rest = location.partition(" ")
    if not separator:
        # A trailing preposition alone carries no location: ask for one instead.
        return "" if location in LEADING_PREPOSITIONS else location
    return rest if first in LEADING_PREPOSITIONS else location


def parse_sms(body: str) -> SmsQuery | None:
    language = parse_language(body)
    text = " ".join(strip_language_directive(body).lower().split())
    zip_codes = set(re.findall(r"\b[0-9]{5}\b", text))
    # Multiple distinct locations need clarification, not a referral for the first ZIP.
    if len(zip_codes) > 1:
        return None
    categories = {CATEGORY_WORDS[match.group()] for match in CATEGORY_PATTERN.finditer(text)}
    # Do not silently choose one service when the sender asked for several.
    if len(categories) > 1:
        return None
    category = next(iter(categories), None)
    if zip_codes:
        return SmsQuery(next(iter(zip_codes)), category, language)
    location = " ".join(CATEGORY_PATTERN.sub("", text).split()).strip(" ,")
    location = _drop_leading_preposition(location)
    return SmsQuery(location, category, language) if location else None


# Twilio rejects any message body over 1,600 characters (error 21617). An over-long
# reply fails outright: the sender gets no resources and no 211/911 guidance.
MAX_MESSAGE_CHARS = 1600

# A line shortened below this carries too little information to be worth sending.
MIN_LINE_BUDGET = 40


def _truncate_line(line: str, budget: int) -> str:
    """Shorten one display line to ``budget`` characters, ending with an ellipsis."""
    body = line[: budget - 1].rstrip()
    # Prefer a word boundary when it keeps most of the content.
    boundary = body.rfind(" ")
    if boundary >= len(body) * 3 // 4:
        body = body[:boundary].rstrip(" ,;:")
    return body + "\u2026"


def _bound_reply(heading: str, lines: list[str], footer: str) -> str:
    """Fit a reply under the provider ceiling without dropping the safety footer.

    Results stay in nearest-first order: keep whole lines while they fit, truncate
    the first line that does not, and drop every farther line. The heading and the
    localized 211/911 footer are never truncated or removed.
    """
    full = "\n".join([heading, *lines, footer])
    if len(full) <= MAX_MESSAGE_CHARS:
        return full
    if len(heading) + len(footer) + 2 > MAX_MESSAGE_CHARS:
        raise ValueError("fixed reply text exceeds the SMS length limit")
    kept: list[str] = []
    for line in lines:
        candidate = "\n".join([heading, *kept, line, footer])
        if len(candidate) <= MAX_MESSAGE_CHARS:
            kept.append(line)
            continue
        budget = MAX_MESSAGE_CHARS - (len(candidate) - len(line))
        if budget >= MIN_LINE_BUDGET:
            kept.append(_truncate_line(line, budget))
        break
    return "\n".join([heading, *kept, footer])


def format_results(
    results: list[ResourceResult], language: Language = Language.ENGLISH
) -> str:
    messages = MESSAGES[language]
    if not results:
        return messages["none"]
    lines = []
    for result in results:
        status = messages["open"] if result.open_now else messages["hours_vary"]
        availability = AVAILABILITY[language][result.availability.value]
        phone = f" {result.resource.phone}" if result.resource.phone else ""
        lines.append(
            f"{result.resource.name} - {result.distance_miles} mi, {status}, "
            f"{messages['availability']} {availability}. {result.resource.address}.{phone}"
        )
    return _bound_reply(messages["heading"], lines, messages["footer"])


def twiml(message: str | None) -> str:
    if message is None:
        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>'
