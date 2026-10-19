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


def test_two_letter_codes_need_the_lang_directive():
    # "so" and "es" are ordinary English words; a bare code must not hijack the reply.
    assert parse_language("need shelter so bad 55415") == Language.ENGLISH
    assert parse_language("es 55415") == Language.ENGLISH
    assert parse_language("so 55415") == Language.ENGLISH
    assert strip_language_directive("need shelter so bad 55415") == "need shelter so bad 55415"
    for code in ("en", "es", "so"):
        assert strip_language_directive(f"55415 lang {code}") == "55415"


def test_language_names_still_work_without_a_directive():
    assert parse_language("somali 55415") == Language.SOMALI
    assert parse_language("spanish 55415") == Language.SPANISH
    assert parse_language("english 55415") == Language.ENGLISH
    assert strip_language_directive("somali 55415") == "55415"


def test_english_so_keeps_location_and_language():
    query = parse_sms("shelter 55415 so cold")
    assert query is not None
    assert query.location == "55415"
    assert query.language == Language.ENGLISH
