import re
from dataclasses import dataclass
from html import escape

from .geocoding import LEADING_PREPOSITIONS
from .i18n import (AVAILABILITY, MESSAGES, Language, language_signal,
                    strip_language_directive)
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
# The language each non-English category word demonstrates. A sender who texts
# entirely in Spanish or Somali gets that language's reviewed templates without
# having to first read English instructions about the "lang" directive.
CATEGORY_WORD_LANGUAGES = {
    "refugio": Language.SPANISH,
    "comida": Language.SPANISH,
    "ducha": Language.SPANISH,
    "centro de calor": Language.SPANISH,
    "hoy": Language.SOMALI,
    "cunto": Language.SOMALI,
    "qubays": Language.SOMALI,
    "meel diirran": Language.SOMALI,
}

CATEGORY_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(word) for word in sorted(CATEGORY_WORDS, key=len, reverse=True)) + r")\b"
)


def detect_language(body: str) -> Language:
    """The reply language: an explicit signal wins; otherwise infer it from the
    sender's own category words, but only when every category word they used
    belongs to a single non-English language. One English word ("comida and
    shelter") or words from two languages veto the guess and keep English -
    the same conservative shape as the bare "es"/"so" code guard."""
    explicit = language_signal(body)
    if explicit is not None:
        return explicit
    text = " ".join(strip_language_directive(body).lower().split())
    words = [match.group() for match in CATEGORY_PATTERN.finditer(text)]
    languages = {CATEGORY_WORD_LANGUAGES.get(word) for word in words}
    if words and None not in languages and len(languages) == 1:
        return next(iter(languages))
    return Language.ENGLISH


@dataclass(frozen=True)
class SmsQuery:
    location: str
    category: ResourceCategory | None
    language: Language = Language.ENGLISH


def parse_sms(body: str) -> SmsQuery | None:
    language = detect_language(body)
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
    # The text keeps its preposition ("shelter in Minneapolis"): the geocoder
    # forgives one leading preposition only after the literal text fails, so
    # "Near North" - a real neighborhood - resolves instead of being mangled to
    # "north". A lone preposition carries no location: ask for one instead.
    location = " ".join(CATEGORY_PATTERN.sub("", text).split()).strip(" ,")
    if not location or location in LEADING_PREPOSITIONS:
        return None
    return SmsQuery(location, category, language)


# Carrier ceilings for concatenated SMS (Twilio's SMS length glossary and error
# 30019): a GSM-7 message carries up to 1,600 characters, but one character
# outside GSM-7 switches the whole message to UCS-2, whose carrier maximum is
# 700 code units. Twilio separately rejects any API call over 1,600 characters
# (error 21617). A reply that cannot be transmitted reaches no one at all - no
# resources and no 211/911 guidance - so a reply is bounded by the ceiling of
# the encoding its content actually needs, not by the API limit alone.
MAX_MESSAGE_CHARS = 1600  # Twilio's API-level limit, any encoding (error 21617)
MAX_GSM7_UNITS = 1600
MAX_UCS2_UNITS = 700

# 3GPP TS 23.038 default alphabet: each basic character costs one unit;
# extension characters cost an escape unit plus their own.
GSM7_BASIC = frozenset(
    "@\u00a3$\u00a5\u00e8\u00e9\u00f9\u00ec\u00f2\u00c7\n\u00d8\u00f8\r\u00c5\u00e5"
    "\u0394_\u03a6\u0393\u039b\u03a9\u03a0\u03a8\u03a3\u0398\u039e\x1b\u00c6\u00e6\u00df\u00c9 "
    "!\"#\u00a4%&'()*+,-./0123456789:;<=>?\u00a1"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ\u00c4\u00d6\u00d1\u00dc\u00a7\u00bf"
    "abcdefghijklmnopqrstuvwxyz\u00e4\u00f6\u00f1\u00fc\u00e0")
GSM7_EXTENSION = frozenset("\x0c^{}\\[~]|\u20ac")

# A line shortened below this carries too little information to be worth sending.
MIN_LINE_BUDGET = 40


def sms_units(text: str) -> tuple[int, int]:
    """(units, ceiling) for the encoding this text forces.

    GSM-7 text is measured in GSM-7 units against the 1,600-character carrier
    maximum; anything containing a character outside GSM-7 is measured in
    UTF-16 code units against the 700-unit UCS-2 carrier maximum.
    """
    units = 0
    for char in text:
        if char in GSM7_BASIC:
            units += 1
        elif char in GSM7_EXTENSION:
            units += 2
        else:
            return len(text.encode("utf-16-le")) // 2, MAX_UCS2_UNITS
    return units, MAX_GSM7_UNITS


def _fits(text: str) -> bool:
    units, ceiling = sms_units(text)
    return units <= ceiling


def _truncate_line(line: str, fits) -> str | None:
    """Shorten one display line until it fits, ending with "...".

    The marker is three GSM-7 dots on purpose: the single-character ellipsis
    (U+2026) is not in the GSM-7 alphabet, so it would flip the whole reply to
    UCS-2 and its 700-unit ceiling - an attempt to fit that fails to send.
    Returns None when the line cannot keep enough text to be worth sending.
    """
    body = line.rstrip()
    while len(body) + 3 >= MIN_LINE_BUDGET:
        # Prefer a word boundary when it keeps most of the content.
        boundary = body.rfind(" ")
        if boundary >= len(body) * 3 // 4:
            body = body[:boundary].rstrip(" ,;:")
        else:
            body = body[:-1].rstrip()
        if fits(body + "..."):
            return body + "..."
    return None


def _bound_reply(heading: str, lines: list[str], footer: str) -> str:
    """Fit a reply under its encoding's carrier ceiling without dropping the
    safety footer.

    Results stay in nearest-first order: keep whole lines while they fit, truncate
    the first line that does not, and drop every farther line. The heading and the
    localized 211/911 footer are never truncated or removed.
    """
    full = "\n".join([heading, *lines, footer])
    if _fits(full):
        return full
    if not _fits("\n".join([heading, footer])):
        raise ValueError("fixed reply text exceeds the SMS length limit")
    kept: list[str] = []
    for line in lines:
        candidate = "\n".join([heading, *kept, line, footer])
        if _fits(candidate):
            kept.append(line)
            continue
        truncated = _truncate_line(
            line, lambda piece: _fits("\n".join([heading, *kept, piece, footer])))
        if truncated is not None:
            kept.append(truncated)
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
