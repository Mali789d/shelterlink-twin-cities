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


def parse_sms(body: str) -> SmsQuery | None:
    language = parse_language(body)
    text = " ".join(strip_language_directive(body).lower().split())
    zip_match = re.search(r"\b\d{5}\b", text)
    categories = {CATEGORY_WORDS[match.group()] for match in CATEGORY_PATTERN.finditer(text)}
    # Do not silently choose one service when the sender asked for several.
    if len(categories) > 1:
        return None
    category = next(iter(categories), None)
    if zip_match:
        return SmsQuery(zip_match.group(), category, language)
    location = " ".join(CATEGORY_PATTERN.sub("", text).split()).strip(" ,")
    return SmsQuery(location, category, language) if location else None


def format_results(
    results: list[ResourceResult], language: Language = Language.ENGLISH
) -> str:
    messages = MESSAGES[language]
    if not results:
        return messages["none"]
    lines = [messages["heading"]]
    for result in results:
        status = messages["open"] if result.open_now else messages["hours_vary"]
        availability = AVAILABILITY[language][result.availability.value]
        phone = f" {result.resource.phone}" if result.resource.phone else ""
        lines.append(
            f"{result.resource.name} - {result.distance_miles} mi, {status}, "
            f"{messages['availability']} {availability}. {result.resource.address}.{phone}"
        )
    lines.append(messages["footer"])
    return "\n".join(lines)


def twiml(message: str | None) -> str:
    if message is None:
        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>'
