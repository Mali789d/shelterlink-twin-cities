from app.i18n import Language, parse_language, strip_language_directive
from app.sms import parse_sms


def test_language_directive_is_detected_and_removed():
    assert parse_language("55415 shelter lang so") == Language.SOMALI
    assert strip_language_directive("55415 shelter lang so") == "55415 shelter"


def test_language_name_is_supported():
    assert parse_language("55415 comida español") == Language.SPANISH


def test_sms_query_preserves_language():
    query = parse_sms("55415 shelter lang es")
    assert query is not None
    assert query.location == "55415"
    assert query.language == Language.SPANISH
