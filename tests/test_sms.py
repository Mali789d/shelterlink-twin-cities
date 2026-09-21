from app.models import ResourceCategory
from app.sms import parse_sms, twiml


def test_parse_zip_and_category():
    query = parse_sms("Need a shelter near 55415")
    assert query is not None
    assert query.location == "55415"
    assert query.category == ResourceCategory.SHELTER


def test_parse_named_location():
    query = parse_sms("Saint Paul food")
    assert query is not None
    assert query.location == "saint paul"
    assert query.category == ResourceCategory.MEAL


def test_twiml_escapes_content():
    xml = twiml("Food & shelter <today>")
    assert "Food &amp; shelter &lt;today&gt;" in xml
