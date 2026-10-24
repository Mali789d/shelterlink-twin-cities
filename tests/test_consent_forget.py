"""Operator-initiated deletion of a sender's consent record (forget).

A sender who asks for their data to be deleted needs a real mechanism before
launch: the durable store otherwise keeps their opt-out hash forever. forget()
removes the record and reports whether one existed. It is deliberately not a
webhook keyword - an unauthenticated text must never erase consent records.
"""
import boto3
import pytest
from botocore.stub import Stubber

from app.keywords import (
    DynamoDBOptOutStore, InMemoryOptOutStore, OptOutStoreUnavailable, hash_phone,
)

PHONE = "+16125550100"
SALT = "private-test-salt-with-32-characters"
KEY = {"phone_hash": {"S": hash_phone(PHONE, SALT)}}


def test_in_memory_forget_reports_whether_a_record_existed():
    store = InMemoryOptOutStore()
    assert store.forget(PHONE) is False
    store.opt_out(PHONE)
    assert store.forget(PHONE) is True
    assert not store.is_opted_out(PHONE)
    assert store.forget(PHONE) is False
    assert store.stored_digests() == frozenset()


def test_in_memory_forget_normalizes_formatted_numbers():
    store = InMemoryOptOutStore()
    store.opt_out("+1 (612) 555-0100")
    assert store.forget(PHONE) is True


def test_in_memory_forget_empty_phone_is_a_noop():
    store = InMemoryOptOutStore()
    store.opt_out(PHONE)
    assert store.forget("") is False
    assert store.is_opted_out(PHONE)


def test_in_memory_forget_respects_salt_isolation():
    store = InMemoryOptOutStore(salt=SALT)
    other = InMemoryOptOutStore(salt="another-private-salt-with-32-chars")
    store.opt_out(PHONE)
    assert other.forget(PHONE) is False
    assert store.is_opted_out(PHONE)


def test_dynamodb_forget_deletes_with_return_values_and_reports_existence():
    client = boto3.client("dynamodb", region_name="us-east-1",
                          aws_access_key_id="test", aws_secret_access_key="test")
    with Stubber(client) as stub:
        stub.add_response(
            "delete_item", {"Attributes": KEY},
            {"TableName": "consent", "Key": KEY, "ReturnValues": "ALL_OLD"})
        stub.add_response(
            "delete_item", {},
            {"TableName": "consent", "Key": KEY, "ReturnValues": "ALL_OLD"})
        store = DynamoDBOptOutStore("consent", SALT, client)
        assert store.forget(PHONE) is True
        assert store.forget(PHONE) is False
        stub.assert_no_pending_responses()


def test_dynamodb_forget_failure_is_fail_closed():
    client = boto3.client("dynamodb", region_name="us-east-1",
                          aws_access_key_id="test", aws_secret_access_key="test")
    with Stubber(client) as stub:
        stub.add_client_error("delete_item", service_error_code="InternalServerError")
        store = DynamoDBOptOutStore("consent", SALT, client)
        with pytest.raises(OptOutStoreUnavailable):
            store.forget(PHONE)


def test_dynamodb_forget_requires_a_sender():
    store = DynamoDBOptOutStore("consent", SALT, client=object())
    with pytest.raises(OptOutStoreUnavailable):
        store.forget("")
