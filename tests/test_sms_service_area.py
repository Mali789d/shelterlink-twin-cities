"""SMS referrals are bounded to the service area.

A texted coordinate far outside the Twin Cities metro must never be answered
with a "nearest" listing hundreds or thousands of miles away: with no map to
judge distance by, that reads as nearby help. Outside the radius the sender
gets the existing no-results reply, which points them to 211.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.main import SMS_SEARCH_RADIUS_MILES, app
from app.search import distance_miles

NYC_COORDS = "40.7128,-74.0060"
DOWNTOWN_MINNEAPOLIS = "44.9778,-93.2650"


def sms_reply(client, body, sender):
    response = client.post("/sms", data={"Body": body, "From": sender})
    assert response.status_code == 200
    match = re.search(r"<Message>(.*?)</Message>", response.text, re.S)
    assert match, f"no <Message> in {response.text!r}"
    return match.group(1)


def test_far_away_coordinates_never_get_a_nearest_listing():
    client = TestClient(app)
    for i, body in enumerate([f"shelter {NYC_COORDS}", f"meal {NYC_COORDS}", NYC_COORDS]):
        reply = sms_reply(client, body, f"+155555502{i:02d}")
        assert "No matching resources found" in reply, body
        assert "Nearest resources" not in reply, body
        assert "Sample" not in reply, body
        # The safety pointers survive: the sender is pointed at current help.
        assert "211" in reply and "911" in reply


def test_in_metro_coordinates_still_return_results():
    client = TestClient(app)
    reply = sms_reply(client, f"meal {DOWNTOWN_MINNEAPOLIS}", "+15555550210")
    assert "Nearest resources" in reply
    assert "Sample Saint Paul Meal Site" in reply


def _point_south_of(latitude, longitude, miles):
    # Walk south along the meridian to a point near the requested distance.
    candidate = latitude
    step = -0.01
    while True:
        candidate += step
        if distance_miles(latitude, longitude, candidate, longitude) >= miles:
            return candidate


def test_radius_boundary_is_enforced_against_real_sample_data():
    # Bracket the radius south of the southernmost sample with wide margins so
    # the assertion never sits on a float boundary.
    just_inside = _point_south_of(44.949, -93.095, SMS_SEARCH_RADIUS_MILES - 1.5)
    just_outside = _point_south_of(44.949, -93.095, SMS_SEARCH_RADIUS_MILES + 1.5)
    assert SMS_SEARCH_RADIUS_MILES - 2 < distance_miles(44.949, -93.095, just_inside, -93.095) \
        < SMS_SEARCH_RADIUS_MILES
    assert SMS_SEARCH_RADIUS_MILES < distance_miles(44.949, -93.095, just_outside, -93.095) \
        < SMS_SEARCH_RADIUS_MILES + 2

    client = TestClient(app)
    inside_reply = sms_reply(client, f"meal {just_inside:.4f},-93.095", "+15555550211")
    assert "Nearest resources" in inside_reply
    outside_reply = sms_reply(client, f"meal {just_outside:.4f},-93.095", "+15555550212")
    assert "No matching resources found" in outside_reply


@pytest.mark.parametrize("directive,expected", [
    ("lang es", "No encontré recursos"),
    ("lang so", "Wax adeeg ah lama helin"),
])
def test_out_of_area_reply_uses_the_senders_language(directive, expected):
    client = TestClient(app)
    reply = sms_reply(client, f"shelter {NYC_COORDS} {directive}", "+15555550213")
    assert expected in reply
    assert "211" in reply and "911" in reply
