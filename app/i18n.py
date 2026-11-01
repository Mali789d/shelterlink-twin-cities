import re
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

# Two-letter codes only count right after "lang": "so" and "es" are ordinary
# English words, and a bare code must not hijack the reply language. Whole
# language names ("somali", "spanish", "español", ...) stay valid on their own.
_DIRECTIVE_CODES = {"en", "es", "so"}
WORD_ALIASES = {key: language for key, language in ALIASES.items()
                if key not in _DIRECTIVE_CODES}

MESSAGES = {
    Language.ENGLISH: {
        "help": "Text a Twin Cities ZIP or location, optionally with shelter, meal, warming, or shower. Add 'lang es' for Spanish or 'lang so' for Somali. ShelterLink Twin Cities. Msg&data rates may apply. Reply STOP to opt out.",
        "opt_in": "ShelterLink Twin Cities: you're subscribed again. Text a ZIP for nearby help. Reply STOP to opt out.",
        "unknown_location": "I couldn't find that location yet. Try a 5-digit Twin Cities ZIP or call 211.",
        "not_live": "ShelterLink is not live yet. For current local help call 211; emergency 911.",
        "none": "No matching resources found. Text another ZIP or call 211 for current local help.",
        "heading": "Nearest resources:",
        "open": "open",
        "hours_vary": "hours vary",
        "availability": "availability",
        "footer": "Info can change. Call first when possible. For current local help call 211; emergency 911.",
    },
    Language.SPANISH: {
        "help": "Envía un código postal o lugar de Twin Cities, con refugio, comida, centro de calor o ducha. ShelterLink Twin Cities. Pueden aplicar tarifas. Responde STOP para cancelar.",
        "opt_in": "ShelterLink Twin Cities: te suscribiste de nuevo. Envía un código postal. Responde STOP para cancelar.",
        "unknown_location": "No encontré ese lugar. Prueba un código postal de 5 dígitos o llama al 211.",
        "not_live": "ShelterLink todavía no está en servicio. Ayuda local actual: 211; emergencia: 911.",
        "none": "No encontré recursos. Envía otro código postal o llama al 211 para ayuda actual.",
        "heading": "Recursos más cercanos:",
        "open": "abierto",
        "hours_vary": "horario variable",
        "availability": "disponibilidad",
        "footer": "La información puede cambiar. Llama primero si puedes. Ayuda local: 211; emergencia: 911.",
    },
    Language.SOMALI: {
        "help": "Soo dir ZIP ama goob Twin Cities ah, kuna dar hoy, cunto, meel diirran, ama qubays. ShelterLink Twin Cities. Kharash fariin ayaa dhici kara. Ku jawaab STOP si aad u joojiso.",
        "opt_in": "ShelterLink Twin Cities: mar kale ayaad ku biirtay. Soo dir ZIP. Ku jawaab STOP si aad u joojiso.",
        "unknown_location": "Goobtaas ma helin. Isku day ZIP 5-lambar ah ama wac 211.",
        "not_live": "ShelterLink weli ma shaqaynayo. Caawimo hadda: wac 211; xaalad degdeg ah: 911.",
        "none": "Wax adeeg ah lama helin. Soo dir ZIP kale ama wac 211 si aad u hesho xogta hadda.",
        "heading": "Adeegyada kuugu dhow:",
        "open": "furan",
        "hours_vary": "saacaduhu way kala duwan yihiin",
        "availability": "helitaan",
        "footer": "Xogtu way is beddeli kartaa. Marka hore wac haddii aad awooddo. Caawimo: 211; xaalad degdeg ah: 911.",
    },
}

# Every nonempty service/consent reply must retain the same reviewed safety footer.
# Reuse existing translations rather than introduce new unreviewed wording.
for templates in MESSAGES.values():
    for kind in ("help", "opt_in", "unknown_location", "none"):
        templates[kind] = templates[kind] + " " + templates["footer"]

AVAILABILITY = {
    Language.ENGLISH: {"available": "available", "full": "full", "unknown": "unknown"},
    Language.SPANISH: {"available": "disponible", "full": "lleno", "unknown": "desconocida"},
    Language.SOMALI: {"available": "waa la heli karaa", "full": "buuxa", "unknown": "lama hubo"},
}


# Senders naturally attach the code with a colon or equals sign ("lang:es",
# "lang=so", "lang : es"). Normalize those to the advertised "lang es" form
# before tokenizing, in both parse_language and strip_language_directive: the
# two tokenize independently, and when they disagree the leftover directive
# becomes the location and a valid city answers "unknown location" in the
# wrong language.
_DIRECTIVE_SEPARATOR = re.compile(r"\blang\s*[:=]\s*", re.IGNORECASE)


def parse_language(text: str) -> Language:
    tokens = _DIRECTIVE_SEPARATOR.sub("lang ", text.lower()).replace(",", " ").split()
    for index, token in enumerate(tokens):
        if token == "lang" and index + 1 < len(tokens):
            return ALIASES.get(tokens[index + 1], Language.ENGLISH)
        if token in WORD_ALIASES:
            return WORD_ALIASES[token]
    return Language.ENGLISH


def strip_language_directive(text: str) -> str:
    # Tokens split on whitespace only: coordinates like "44.9,-93.2" keep the
    # comma they need. The "lang" directive is the one form whose code can
    # attach with a comma ("lang,es") or a colon/equals sign ("lang:es",
    # normalized by _DIRECTIVE_SEPARATOR): parse_language treats those as
    # separators and detects them, so they must be removed here too, or the
    # leftover text becomes the location and a valid city answers "unknown
    # location" in the sender's own language.
    tokens = _DIRECTIVE_SEPARATOR.sub("lang ", text).split()
    cleaned: list[str] = []
    skip_next = False
    for index, token in enumerate(tokens):
        lowered = token.lower()
        if skip_next:
            # Commas-only filler between "lang" and its code ("lang , es")
            # belongs to the directive; keep skipping until the code token.
            if not token.strip(","):
                continue
            skip_next = False
            continue
        head, _, attached = lowered.partition(",")
        is_directive = head == "lang" and (attached or index + 1 < len(tokens))
        if is_directive:
            if attached.strip(","):
                continue  # "lang,es" carries its code in the same token
            skip_next = True
            continue
        if lowered.strip(",") in WORD_ALIASES:
            continue
        cleaned.append(token)
    return " ".join(cleaned)
