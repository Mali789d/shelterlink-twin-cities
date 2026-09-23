import re
from dataclasses import dataclass
from html import escape

from .i18n import AVAILABILITY, MESSAGES, Language, parse_language, strip_language_directive
from .models import ResourceCategory, ResourceResult

CATEGORY_WORDS = {
    "shelter": ResourceCategory.SHELTER,
    "bed": ResourceCategory.SHELTER,
    "meal": ResourceCategory.MEAL,
    "food": ResourceCategory.MEAL,
    "warm": ResourceCategory.WARMING,
    "warming": ResourceCategory.WARMING,
    "shower": ResourceCategory.SHOWER,
}


@dataclass(frozen=True)
class SmsQuery:
    location: str
    category: ResourceCategory | None
    language: Language = Language.ENGLISH


def parse_sms(body: str) -> SmsQuery | None:
    language = parse_language(body)
    text = " ".join(strip_language_directive(body).lower().split())
    zip_match = re.search(r"\b\d{5}\b", text)
    category = next((value for word, value in CATEGORY_WORDS.items() if word in text), None)
    if zip_match:
        return SmsQuery(zip_match.group(), category, language)
    location = re.sub(r"\b(shelter|bed|meal|food|warm|warming|shower)\b", "", text).strip(" ,")
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


def twiml(message: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>'
