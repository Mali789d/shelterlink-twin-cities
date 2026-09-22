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


def test_formatted_message_uses_safe_result_availability():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.data import load_resources
    from app.search import find_resources
    from app.sms import format_results

    observed = datetime(2026, 9, 23, 12, tzinfo=ZoneInfo("America/Chicago"))
    message = format_results(find_resources(load_resources(), 44.9778, -93.2650, at=observed))
    assert "availability unknown" in message
    assert "availability available" not in message
