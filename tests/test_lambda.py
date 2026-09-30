"""Exercise the packaged entry point with API Gateway HTTP API v2 events."""

import json
from urllib.parse import urlencode

from app.lambda_handler import handler
from app.security import compute_signature


def event(path, method="GET", body=None, headers=None, query=""):
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": query,
        "headers": {"host": "test.execute-api.us-east-1.amazonaws.com", **(headers or {})},
        "requestContext": {
            "http": {"method": method, "path": path, "sourceIp": "127.0.0.1"},
            "domainName": "test.execute-api.us-east-1.amazonaws.com",
            "stage": "$default",
        },
        "isBase64Encoded": False,
        "body": body,
    }


def test_lambda_health_and_notice():
    result = handler(event("/health"), None)
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["status"] == "ok"
    notice = handler(event("/privacy"), None)
    assert notice["statusCode"] == 200
    assert "Prototype, not a live service" in notice["body"]


def test_lambda_unsigned_sms_fails_closed_in_production(monkeypatch):
    monkeypatch.setenv("SHELTERLINK_ENV", "production")
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    body = urlencode({"Body": "55415 shelter", "From": "+16125550100"})
    result = handler(event("/sms", "POST", body, {"content-type": "application/x-www-form-urlencoded"}), None)
    assert result["statusCode"] == 503


def test_lambda_signed_sms_twiml(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "get_opt_out_store", lambda: main.InMemoryOptOutStore("test"))
    monkeypatch.setenv("SHELTERLINK_ENV", "production")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://test.execute-api.us-east-1.amazonaws.com")
    form = {"Body": "55415 shelter", "From": "+16125550100"}
    signature = compute_signature("test-token", "https://test.execute-api.us-east-1.amazonaws.com/sms", form)
    result = handler(event("/sms", "POST", urlencode(form), {
        "content-type": "application/x-www-form-urlencoded",
        "x-twilio-signature": signature,
    }), None)
    assert result["statusCode"] == 200
    assert "not live yet" in result["body"]
    assert "211" in result["body"] and "911" in result["body"]
    assert "Sample" not in result["body"]
    assert result["headers"]["content-type"].startswith("application/xml")


def test_template_has_explicit_routes_and_production_fail_closed():
    # Check the deployment contract without adding YAML as a production dependency.
    text = open("template.yaml").read()
    for fragment in (
        "Handler: app.lambda_handler.handler", "Runtime: python3.12",
        "SHELTERLINK_ENV: production", "Path: /sms, Method: POST",
        "Path: /privacy, Method: GET", "Path: /terms, Method: GET",
    ):
        assert fragment in text


def test_template_retains_consent_and_limits_permissions():
    text = open("template.yaml").read()
    for fragment in (
        "DeletionPolicy: Retain", "UpdateReplacePolicy: Retain",
        "AttributeName: phone_hash",
    ):
        assert fragment in text
    for fragment in (
        "NoEcho: true", "MinLength: 32", "OPT_OUT_TABLE: !Ref OptOutTable",
        "OPT_OUT_HASH_SALT: !Ref OptOutHashSalt", "SSEEnabled: true",
        "Resource: !GetAtt OptOutTable.Arn", "dynamodb:GetItem",
        "dynamodb:PutItem", "dynamodb:DeleteItem",
    ):
        assert fragment in text
    assert "dynamodb:*" not in text
    assert "TimeToLiveSpecification" not in text
