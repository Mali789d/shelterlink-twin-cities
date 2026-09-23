from enum import Enum


class Language(str, Enum):
    ENGLISH = "en"
    SPANISH = "es"
    SOMALI = "so"


ALIASES = {
    "en": Language.ENGLISH,
    "english": Language.ENGLISH,
    "es": Language.SPANISH,
    "español": Language.SPANISH,
    "espanol": Language.SPANISH,
    "spanish": Language.SPANISH,
    "so": Language.SOMALI,
    "somali": Language.SOMALI,
    "af-soomaali": Language.SOMALI,
}

MESSAGES = {
    Language.ENGLISH: {
        "help": "Text a Twin Cities ZIP or location, optionally with shelter, meal, warming, or shower. Add 'lang es' for Spanish or 'lang so' for Somali.",
        "unknown_location": "I couldn't find that location yet. Try a 5-digit Twin Cities ZIP or call 211.",
        "none": "No matching resources found. Text another ZIP or call 211 for current local help.",
        "heading": "Nearest resources:",
        "open": "open",
        "hours_vary": "hours vary",
        "availability": "availability",
        "footer": "Info can change. Call first when possible. For current local help call 211; emergency 911.",
    },
    Language.SPANISH: {
        "help": "Envía un código postal o lugar de Twin Cities, con refugio, comida, centro de calor o ducha.",
        "unknown_location": "No encontré ese lugar. Prueba un código postal de 5 dígitos o llama al 211.",
        "none": "No encontré recursos. Envía otro código postal o llama al 211 para ayuda actual.",
        "heading": "Recursos más cercanos:",
        "open": "abierto",
        "hours_vary": "horario variable",
        "availability": "disponibilidad",
        "footer": "La información puede cambiar. Llama primero si puedes. Ayuda local: 211; emergencia: 911.",
    },
    Language.SOMALI: {
        "help": "Soo dir ZIP ama goob Twin Cities ah, kuna dar hoy, cunto, meel diirran, ama qubays.",
        "unknown_location": "Goobtaas ma helin. Isku day ZIP 5-lambar ah ama wac 211.",
        "none": "Wax adeeg ah lama helin. Soo dir ZIP kale ama wac 211 si aad u hesho xogta hadda.",
        "heading": "Adeegyada kuugu dhow:",
        "open": "furan",
        "hours_vary": "saacaduhu way kala duwan yihiin",
        "availability": "helitaan",
        "footer": "Xogtu way is beddeli kartaa. Marka hore wac haddii aad awooddo. Caawimo: 211; xaalad degdeg ah: 911.",
    },
}

AVAILABILITY = {
    Language.ENGLISH: {"available": "available", "full": "full", "unknown": "unknown"},
    Language.SPANISH: {"available": "disponible", "full": "lleno", "unknown": "desconocida"},
    Language.SOMALI: {"available": "waa la heli karaa", "full": "buuxa", "unknown": "lama hubo"},
}


def parse_language(text: str) -> Language:
    tokens = text.lower().replace(",", " ").split()
    for index, token in enumerate(tokens):
        if token == "lang" and index + 1 < len(tokens):
            return ALIASES.get(tokens[index + 1], Language.ENGLISH)
        if token in ALIASES:
            return ALIASES[token]
    return Language.ENGLISH


def strip_language_directive(text: str) -> str:
    tokens = text.split()
    cleaned: list[str] = []
    skip_next = False
    for index, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        normalized = token.lower().strip(",")
        if normalized == "lang" and index + 1 < len(tokens):
            skip_next = True
            continue
        if normalized in ALIASES:
            continue
        cleaned.append(token)
    return " ".join(cleaned)
