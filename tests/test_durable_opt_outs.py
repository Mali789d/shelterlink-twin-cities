"""Local persistence contract and exact AWS API requests, with no network calls."""
import boto3
import pytest
from botocore.stub import Stubber
from fastapi.testclient import TestClient

import app.main as main
from app.keywords import DynamoDBOptOutStore, OptOutStoreUnavailable, hash_phone
from app.security import compute_signature

PHONE = "+16125550100"
KEY = {"phone_hash": {"S": hash_phone(PHONE, "private-test-salt-with-32-characters")}}


@pytest.mark.parametrize("table,salt", [("", "secret"), ("consent", ""), ("consent", "dev-salt"), ("consent", "short")])
def test_no_unsafe_configuration(table, salt):
    with pytest.raises(OptOutStoreUnavailable):
        DynamoDBOptOutStore(table, salt)


def test_aws_requests_store_only_digest_and_read_consistently():
    client = boto3.client("dynamodb", region_name="us-east-1",
                          aws_access_key_id="test", aws_secret_access_key="test")
    with Stubber(client) as stub:
        stub.add_response("put_item", {}, {"TableName": "consent", "Item": KEY})
        stub.add_response("get_item", {"Item": KEY},
                          {"TableName": "consent", "Key": KEY, "ConsistentRead": True})
        stub.add_response("delete_item", {}, {"TableName": "consent", "Key": KEY})
        stub.add_response("get_item", {},
                          {"TableName": "consent", "Key": KEY, "ConsistentRead": True})
        store = DynamoDBOptOutStore("consent", "private-test-salt-with-32-characters", client)
        store.opt_out(PHONE)
        assert store.is_opted_out(PHONE)
        store.opt_in(PHONE)
        assert not store.is_opted_out(PHONE)
        stub.assert_no_pending_responses()


class SharedDatabase:
    def __init__(self):
        self.items = {}
        self.fail = False

    def check(self):
        if self.fail:
            raise RuntimeError("private provider details")

    def put_item(self, TableName, Item):
        self.check()
        self.items[Item["phone_hash"]["S"]] = Item
        return {}

    def get_item(self, TableName, Key, ConsistentRead):
        self.check()
        assert ConsistentRead is True
        item = self.items.get(Key["phone_hash"]["S"])
        return {"Item": item} if item else {}

    def delete_item(self, TableName, Key):
        self.check()
        self.items.pop(Key["phone_hash"]["S"], None)
        return {}


def signed_sms(body, sender=PHONE):
    form = {"Body": body, "From": sender}
    signature = compute_signature("test-token", "https://sms.example/sms", form)
    return TestClient(main.app).post("/sms", data=form,
                                   headers={"X-Twilio-Signature": signature})


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setenv("SHELTERLINK_ENV", "production")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://sms.example")


def test_stop_survives_new_instance_and_start_removes_it(monkeypatch, production):
    database = SharedDatabase()
    # A new store for every request simulates separate Lambda instances.
    monkeypatch.setattr(main, "get_opt_out_store", lambda:
                        DynamoDBOptOutStore("consent", "private-test-salt-with-32-characters", database))
    assert "<Message>" not in signed_sms("STOP").text
    assert "<Message>" not in signed_sms("55415 shelter").text
    assert "not live yet" in signed_sms("55415 shelter", "+16125550199").text
    assert "ShelterLink" in signed_sms("HELP").text
    assert "subscribed again" in signed_sms("START").text
    assert "not live yet" in signed_sms("55415 shelter").text
    assert database.items == {}


@pytest.mark.parametrize("body", ["STOP", "START", "55415 shelter"])
def test_outage_fails_closed_without_reply_or_leaked_error(monkeypatch, production, body):
    database = SharedDatabase()
    database.fail = True
    monkeypatch.setattr(main, "get_opt_out_store", lambda:
                        DynamoDBOptOutStore("consent", "private-test-salt-with-32-characters", database))
    response = signed_sms(body)
    assert response.status_code == 503
    assert "<Message>" not in response.text
    assert "private provider details" not in response.text


def test_production_cannot_fall_back_to_memory(monkeypatch, production):
    monkeypatch.delenv("OPT_OUT_TABLE", raising=False)
    monkeypatch.delenv("OPT_OUT_HASH_SALT", raising=False)
    assert signed_sms("55415 shelter").status_code == 503
    assert signed_sms("START").status_code == 503


def test_missing_sender_is_rejected(production):
    assert signed_sms("START", "").status_code == 400
