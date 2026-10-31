"""Every category the HELP reply advertises must answer end-to-end in the prototype.

The HELP replies invite people to text "shelter, meal, warming, or shower"
(refugio/comida/centro de calor/ducha, hoy/cunto/meel diirran/qubays). A category
with no sample listing answers "No matching resources found" every single time,
which makes the advertised word look broken in any demo or local test. Every
sample stays clearly marked non-live: is_sample excludes it from open_now and
from any production-mode directory.
"""
import pytest
from fastapi.testclient import TestClient

from app.data import load_resources
from app.main import app
from app.models import ResourceCategory

client = TestClient(app)


def test_every_advertised_category_has_a_sample_listing():
    categories = {resource.category for resource in load_resources()}
    assert categories == set(ResourceCategory), (
        "the HELP replies advertise every ResourceCategory; each needs a sample")
    assert all(resource.is_sample for resource in load_resources())


@pytest.mark.parametrize("body,name", [
    ("shelter 55401", "Sample Minneapolis Shelter"),
    ("meal 55101", "Sample Saint Paul Meal Site"),
    ("warming 55411", "Sample Minneapolis Warming Center"),
    ("shower 55103", "Sample Saint Paul Shower Site"),
])
def test_each_advertised_category_answers_by_zip(body, name):
    response = client.post("/sms", data={"Body": body, "From": "+15555550166"})
    assert response.status_code == 200
    assert name in response.text
    assert "211" in response.text and "911" in response.text


@pytest.mark.parametrize("body,name", [
    ("warming near north", "Sample Minneapolis Warming Center"),
    ("shower near frogtown", "Sample Saint Paul Shower Site"),
    ("ducha 55103", "Sample Saint Paul Shower Site"),
    ("qubays 55103", "Sample Saint Paul Shower Site"),
    ("centro de calor 55411", "Sample Minneapolis Warming Center"),
    ("meel diirran 55411", "Sample Minneapolis Warming Center"),
])
def test_categories_answer_by_neighborhood_and_in_every_language(body, name):
    # Yesterday's neighborhood names and the reviewed Spanish/Somali category
    # words reach the new samples too - no English-only surface.
    response = client.post("/sms", data={"Body": body, "From": "+15555550166"})
    assert response.status_code == 200
    assert name in response.text


def test_new_samples_never_present_as_open_or_current():
    response = client.post("/sms", data={"Body": "warming 55411", "From": "+15555550166"})
    assert ", open, " not in response.text
    assert "availability available" not in response.text
    assert "hours vary" in response.text
