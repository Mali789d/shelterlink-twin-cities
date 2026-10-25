"""The per-sender reply throttle bounds paid SMS traffic without blocking consent."""
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.throttle import DEFAULT_MAX_REPLIES, ReplyThrottle


def post_sms(body="55415 shelter", sender="+15555550100"):
    return TestClient(main.app).post("/sms", data={"Body": body, "From": sender})


def make_throttle(**kwargs):
    state = {"now": 1000.0}
    kwargs.setdefault("now", lambda: state["now"])
    return state, ReplyThrottle(**kwargs)


def test_allows_up_to_the_limit_then_stays_silent():
    _, throttle = make_throttle(max_replies=3, window_seconds=3600)
    assert [throttle.allow("+1") for _ in range(3)] == [True, True, True]
    assert throttle.allow("+1") is False
    assert throttle.allow("+1") is False


def test_window_slides_and_replies_resume():
    state, throttle = make_throttle(max_replies=2, window_seconds=3600)
    assert throttle.allow("+1") and throttle.allow("+1")
    assert throttle.allow("+1") is False
    state["now"] += 3601
    assert throttle.allow("+1") is True


def test_window_slides_per_reply_not_all_at_once():
    state, throttle = make_throttle(max_replies=2, window_seconds=60)
    assert throttle.allow("+1")
    state["now"] += 30
    assert throttle.allow("+1")
    state["now"] += 31  # first reply aged out, second has 29s left
    assert throttle.allow("+1") is True
    assert throttle.allow("+1") is False


def test_senders_have_independent_budgets():
    _, throttle = make_throttle(max_replies=1, window_seconds=3600)
    assert throttle.allow("+1") is True
    assert throttle.allow("+1") is False
    assert throttle.allow("+2") is True


def test_least_active_sender_is_evicted_past_the_tracking_ceiling():
    _, throttle = make_throttle(max_replies=1, window_seconds=3600,
                                max_tracked_senders=3)
    for sender in ("+1", "+2", "+3"):
        throttle.allow(sender)
    throttle.allow("+4")                # evicts +1, the least recently active
    assert throttle.allow("+1") is True   # tracked fresh with a new budget
    assert throttle.allow("+3") is False  # still tracked and throttled
    assert throttle.allow("+4") is False


def test_env_override_changes_the_budget():
    throttle = ReplyThrottle.from_env({"SHELTERLINK_SMS_REPLY_LIMIT": " 2 "})
    assert [throttle.allow("+1") for _ in range(2)] == [True, True]
    assert throttle.allow("+1") is False


def test_invalid_env_values_fall_back_to_defaults():
    throttle = ReplyThrottle.from_env({"SHELTERLINK_SMS_REPLY_LIMIT": "junk",
                                       "SHELTERLINK_SMS_REPLY_WINDOW_SECONDS": "-5"})
    assert [throttle.allow("+1") for _ in range(DEFAULT_MAX_REPLIES)] == [True] * 5
    assert throttle.allow("+1") is False


def test_constructor_rejects_nonpositive_limits():
    with pytest.raises(ValueError):
        ReplyThrottle(max_replies=0)


@pytest.fixture
def throttled(monkeypatch):
    state = {"now": 1000.0}
    throttle = ReplyThrottle(max_replies=3, window_seconds=3600,
                           now=lambda: state["now"])
    monkeypatch.setattr(main, "reply_throttle", throttle)
    yield state
    main.opt_outs.forget("+15555550701")
    main.opt_outs.forget("+15555550702")


def test_webhook_stops_paying_for_replies_past_the_budget(throttled):
    for _ in range(3):
        assert "<Message>" in post_sms(sender="+15555550701").text
    response = post_sms(sender="+15555550701")
    assert response.status_code == 200
    assert "<Message>" not in response.text
    # An empty TwiML answer is a 200, so Twilio does not retry the webhook.


def test_throttled_budget_recovers_after_the_window(throttled):
    for _ in range(3):
        post_sms(sender="+15555550701")
    assert "<Message>" not in post_sms(sender="+15555550701").text
    throttled["now"] += 3601
    assert "<Message>" in post_sms(sender="+15555550701").text


def test_one_sender_throttled_leaves_others_alone(throttled):
    for _ in range(3):
        post_sms(sender="+15555550701")
    assert "<Message>" not in post_sms(sender="+15555550701").text
    assert "<Message>" in post_sms(sender="+15555550702").text


def test_consent_keywords_are_never_throttled(throttled):
    sender = "+15555550701"
    for _ in range(3):
        post_sms(sender=sender)
    assert "<Message>" not in post_sms(sender=sender).text
    response = post_sms("STOP", sender=sender)
    assert response.status_code == 200
    assert main.opt_outs.is_opted_out(sender)
    response = post_sms("START", sender=sender)
    assert "subscribed again" in response.text
    response = post_sms("HELP", sender=sender)
    assert "ShelterLink Twin Cities" in response.text


def test_guidance_replies_also_count_against_the_budget(throttled):
    # An unparseable text still earns a paid guidance reply, so it counts too.
    for _ in range(3):
        assert "<Message>" in post_sms("hello", sender="+15555550701").text
    assert "<Message>" not in post_sms("hello", sender="+15555550701").text
