"""Every HTTP response carries its cache and browser-safety policy with it.

An SMS reply is computed for one sender's location, and search results carry
live availability claims: a shared cache replaying either serves a stale
"open"/"available" answer as current - the exact harm this service exists to
prevent - or one person's referral to another person. Personalized endpoints
are therefore no-store, and every response gets baseline browser protections.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
https_client = TestClient(app, base_url="https://testserver")

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def test_sms_replies_are_never_stored_by_a_shared_cache():
    response = client.post("/sms", data={"Body": "55415", "From": "+15555550178"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"


def test_sms_error_replies_are_never_stored_either():
    # A cached 4xx replayed for a valid request would deny help; errors carry
    # the same policy as successful replies.
    response = client.post("/sms", data={"Body": "55415"})  # missing sender
    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "no-store"


def test_search_results_and_errors_are_never_stored():
    ok = client.get("/resources/search", params={"location": "55415"})
    assert ok.status_code == 200
    assert ok.headers["Cache-Control"] == "no-store"
    bad = client.get("/resources/search", params={"location": "nowhere particular"})
    assert bad.status_code == 400
    assert bad.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("make_request", [
    lambda: client.get("/health"),
    lambda: client.get("/ready"),
    lambda: client.get("/privacy"),
    lambda: client.get("/terms"),
    lambda: client.post("/sms", data={"Body": "55415", "From": "+15555550178"}),
    lambda: client.get("/no-such-route"),
])
def test_baseline_browser_protections_on_every_response(make_request):
    response = make_request()
    for name, expected in BASE_HEADERS.items():
        assert response.headers[name] == expected


def test_readiness_keeps_a_single_explicit_no_store():
    # The endpoint sets Cache-Control itself; the middleware must not stack a
    # second copy on top of it.
    response = client.get("/ready")
    assert response.headers.get_list("cache-control") == ["no-store"]


def test_html_notice_pages_get_a_deny_by_default_csp():
    for path in ("/privacy", "/terms"):
        response = client.get(path)
        assert response.headers["content-type"].startswith("text/html")
        csp = response.headers["Content-Security-Policy"]
        # The pages use one inline stylesheet and nothing else: no scripts,
        # images, frames, connections or alternate base URI.
        assert "default-src 'none'" in csp
        assert "style-src 'unsafe-inline'" in csp
        assert "base-uri 'none'" in csp
        assert "frame-ancestors 'none'" in csp


def test_csp_is_scoped_to_html_responses_only():
    for response in (client.get("/health"),
                     client.post("/sms", data={"Body": "55415", "From": "+15555550178"})):
        assert not response.headers["content-type"].startswith("text/html")
        assert "Content-Security-Policy" not in response.headers


def test_hsts_is_sent_only_over_https():
    # Browsers ignore HSTS over plain HTTP, so local development stays simple;
    # behind a TLS-terminating deployment the header goes out.
    assert https_client.get("/health").headers["Strict-Transport-Security"] == "max-age=31536000"
    assert "Strict-Transport-Security" not in client.get("/health").headers
