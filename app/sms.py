import re
from dataclasses import dataclass
from html import escape

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


def parse_sms(body: str) -> SmsQuery | None:
    text = " ".join(body.lower().split())
    zip_match = re.search(r"\b\d{5}\b", text)
    category = next((value for word, value in CATEGORY_WORDS.items() if word in text), None)
    if zip_match:
        return SmsQuery(zip_match.group(), category)
    location = re.sub(r"\b(shelter|bed|meal|food|warm|warming|shower)\b", "", text).strip(" ,")
    return SmsQuery(location, category) if location else None


def format_results(results: list[ResourceResult]) -> str:
    if not results:
        return "No matching resources found. Text another ZIP or call 211 for current local help."
    lines = ["Nearest resources:"]
    for result in results:
        status = "open" if result.open_now else "hours vary"
        availability = result.resource.availability.value
        phone = f" {result.resource.phone}" if result.resource.phone else ""
        lines.append(
            f"{result.resource.name} - {result.distance_miles} mi, {status}, "
            f"availability {availability}. {result.resource.address}.{phone}"
        )
    lines.append("Info can change. Call first when possible. For current local help call 211; emergency 911.")
    return "\n".join(lines)


def twiml(message: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>'
