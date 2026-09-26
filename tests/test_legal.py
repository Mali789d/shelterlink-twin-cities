from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_notices_are_public_readable_html_with_crosslinks():
    for path, title in (("/privacy", "Privacy"), ("/terms", "Terms")):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "<main>" in response.text
        assert f"<h1>{title}</h1>" in response.text
        assert '<a href="/privacy">' in response.text
        assert '<a href="/terms">' in response.text
        assert "Call 211" in response.text
        assert "911" in response.text
        assert "Prototype, not a live service" in response.text


def test_privacy_is_honest_about_current_data_handling():
    text = client.get("/privacy").text
    for fact in ("phone number", "message", "sample resource listings", "public SMS number yet", "salted hashes", "disappears on restart", "SMS provider", "data-retention"):
        assert fact in text


def test_terms_do_not_claim_live_availability_or_free_texting():
    text = client.get("/terms").text
    for fact in ("not a public emergency", "may not correspond", "Do not travel", "message and data rates", "STOP", "START", "HELP"):
        assert fact in text
