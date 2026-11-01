from app.geocoding import DevelopmentGeocoder, parse_coordinates
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


# Every spelling parse_language accepts as a directive must also be the text
# strip_language_directive removes. The two tokenize messages independently;
# when they disagree, the leftover directive becomes the location and a valid
# city answers "unknown location" in the sender's own language.
DIRECTIVE_SPELLINGS = [
    ("lang es", Language.SPANISH),
    ("lang,es", Language.SPANISH),
    ("lang, es", Language.SPANISH),
    ("lang ,es", Language.SPANISH),
    ("lang , es", Language.SPANISH),
    ("lang,es,", Language.SPANISH),
    ("LANG ES", Language.SPANISH),
    ("lang  es", Language.SPANISH),
    ("lang\tes", Language.SPANISH),
    ("lang espanol", Language.SPANISH),
    ("lang,espanol", Language.SPANISH),
    ("lang español", Language.SPANISH),
    ("lang so", Language.SOMALI),
    ("lang,so", Language.SOMALI),
    ("lang somali", Language.SOMALI),
    ("lang en", Language.ENGLISH),
    ("lang:es", Language.SPANISH),
    ("lang: es", Language.SPANISH),
    ("lang :es", Language.SPANISH),
    ("lang : es", Language.SPANISH),
    ("lang:es,", Language.SPANISH),
    ("LANG:ES", Language.SPANISH),
    ("lang=es", Language.SPANISH),
    ("lang:espanol", Language.SPANISH),
    ("lang:so", Language.SOMALI),
    ("lang=somali", Language.SOMALI),
    ("lang:english", Language.ENGLISH),
    ("lang:en", Language.ENGLISH),
]


def test_directive_spellings_are_detected_and_removed_identically():
    for spelling, language in DIRECTIVE_SPELLINGS:
        text = f"{spelling} minneapolis"
        assert parse_language(text) is language, spelling
        assert strip_language_directive(text) == "minneapolis", spelling


def test_directive_spellings_never_corrupt_the_sms_location():
    for spelling, language in DIRECTIVE_SPELLINGS:
        query = parse_sms(f"{spelling} minneapolis")
        assert query is not None, spelling
        assert query.location == "minneapolis", spelling
        assert query.language is language, spelling


def test_directive_only_message_asks_for_a_location():
    # A bare directive has no location to find: answer with help, not "unknown".
    for spelling, _language in DIRECTIVE_SPELLINGS:
        assert parse_sms(spelling) is None, spelling


def test_place_commas_survive_directive_stripping():
    # Commas inside a place name are not directives: "St. Paul, MN" still
    # resolves to the city through parse_sms and the geocoder.
    query = parse_sms("st. paul, mn")
    assert query is not None
    assert DevelopmentGeocoder().geocode(query.location) is not None
    assert query.language is Language.ENGLISH


def test_texted_coordinates_keep_their_comma():
    # Directive removal must not eat the comma "lat,lng" coordinates need.
    query = parse_sms("shelter 44.9778,-93.2650")
    assert query is not None
    assert query.location == "44.9778,-93.2650"
    spaced = parse_sms("shelter 44.9778, -93.2650")
    assert spaced is not None
    assert parse_coordinates(spaced.location) is not None


def test_colon_attached_directive_replies_in_the_senders_language():
    # Regression: "refugio minneapolis lang:es" used to leave "lang:es" in the
    # location and answer "unknown location" in English.
    import re

    from fastapi.testclient import TestClient

    from app.main import app
    client = TestClient(app)
    for i, (body, expected) in enumerate([
        ("refugio minneapolis lang:es", "Recursos más cercanos"),
        ("cunto 55103 lang:so", "Adeegyada kuugu dhow"),
        ("shelter 55415 lang=english", "Nearest resources"),
    ]):
        response = client.post("/sms", data={"Body": body, "From": f"+155555503{i:02d}"})
        assert response.status_code == 200
        message = re.search(r"<Message>(.*?)</Message>", response.text, re.S).group(1)
        assert expected in message, body
        assert "211" in message and "911" in message
