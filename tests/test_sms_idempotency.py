"""Twilio redeliveries replay the cached response instead of paying for a second reply."""
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.idempotency import ReplyCache


def post_sms(body="55415 shelter", sender="+15555550100", sid="SM1000000000000000000000000000001"):
    data = {"Body": body, "From": sender}
    if sid:
        data["MessageSid"] = sid
    return TestClient(main.app).post("/sms", data=data)


def make_cache(**kwargs):
    state = {"now": 1000.0}
    kwargs.setdefault("now", lambda: state["now"])
    return state, ReplyCache(**kwargs)


def test_cached_reply_survives_until_the_ttl():
    state, cache = make_cache(ttl_seconds=60)
    cache.put("SM1", "<Response><Message>hi</Message></Response>")
    assert cache.get("SM1") == "<Response><Message>hi</Message></Response>"
    state["now"] += 61
    assert cache.get("SM1") is None


def test_oldest_entry_is_evicted_past_the_ceiling():
    _, cache = make_cache(max_entries=2)
    cache.put("SM1", "one")
    cache.put("SM2", "two")
    cache.put("SM3", "three")
    assert cache.get("SM1") is None
    assert cache.get("SM2") == "two"
    assert cache.get("SM3") == "three"


def test_constructor_rejects_nonpositive_limits():
    with pytest.raises(ValueError):
        ReplyCache(ttl_seconds=0)
    with pytest.raises(ValueError):
        ReplyCache(max_entries=0)


def test_redelivery_replays_the_identical_reply():
    sid = "SM2000000000000000000000000000001"
    first = post_sms(sid=sid)
    assert "<Message>" in first.text
    second = post_sms(sid=sid)
    assert second.text == first.text


def test_redelivery_does_not_consume_the_reply_budget():
    sender = "+15555550710"
    sid = "SM2000000000000000000000000000002"
    for _ in range(3):
        assert "<Message>" in post_sms(sid=sid, sender=sender).text
    # All three were the same logical message: the budget spent exactly one slot,
    # and redeliveries keep replaying the cached reply past the third repeat.
    assert "<Message>" in post_sms(sid=sid, sender=sender).text
    # A genuinely new message from the same sender spends fresh budget.
    assert "<Message>" in post_sms(sender=sender, sid="SM2000000000000000000000000000003").text


def test_distinct_message_ids_are_processed_independently():
    first = post_sms(sid="SM2000000000000000000000000000004")
    second = post_sms(sid="SM2000000000000000000000000000005")
    assert "<Message>" in first.text and "<Message>" in second.text


def test_requests_without_a_message_id_behave_as_before():
    response = post_sms(sid=None)
    assert response.status_code == 200
    assert "<Message>" in response.text


def test_throttled_redelivery_stays_silent_but_uncached_failures_reprocess(monkeypatch):
    sender = "+15555550711"
    sid = "SM2000000000000000000000000000006"
    throttle = main.reply_throttle
    assert throttle.allow(sender) and throttle.allow(sender)
    assert throttle.allow(sender) and throttle.allow(sender) and throttle.allow(sender)
    # Budget exhausted by earlier messages: this delivery is throttled (200, empty).
    silent = post_sms(sender=sender, sid=sid)
    assert "<Message>" not in silent.text
    # The empty 200 IS a successful answer: a redelivery replays it and still
    # spends nothing.
    assert "<Message>" not in post_sms(sender=sender, sid=sid).text


def test_consent_outage_response_is_never_cached(monkeypatch):
    sid = "SM2000000000000000000000000000007"
    monkeypatch.setattr(main, "get_opt_out_store", _UnavailableStore)
    response = post_sms(sid=sid)
    assert response.status_code == 503
    monkeypatch.undo()
    # After the store recovers, the same delivery is processed for real.
    recovered = post_sms(sid=sid)
    assert recovered.status_code == 200
    assert "<Message>" in recovered.text


class _UnavailableStore:
    def __init__(self):
        raise RuntimeError("consent storage down")
