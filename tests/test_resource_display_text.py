"""Provider text must not break XML or inject extra SMS lines."""
import json
import xml.etree.ElementTree as ET

import pytest

from app.data import DATA_PATH, load_resources
from app.models import Resource
from app.sms import twiml


@pytest.mark.parametrize("field", ["id", "name", "address", "source_name", "phone"])
@pytest.mark.parametrize("control", ["\x00", "\x01", "\n", "\r", "\t", "\x7f", "\x85", "\u2028", "\u2029"])
def test_controls_and_line_breaks_reject_whole_snapshot(tmp_path, field, control):
    data = json.loads(DATA_PATH.read_text())
    data[-1][field] = "before" + control + "after"
    path = tmp_path / "resources.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="control characters"):
        load_resources(path)


@pytest.mark.parametrize("text", ["Centro de atención", "Hoyga qoyska", "O'Brien & Sons <help>",
                                  "明尼阿波利斯", "Resource 🏠"])
def test_legitimate_multilingual_and_escaped_text_remains_supported(text):
    data = json.loads(DATA_PATH.read_text())[0]
    data["name"] = text
    item = Resource.model_validate(data)
    assert item.name == text
    assert ET.fromstring(twiml(item.name)).find("Message").text == text


def test_optional_phone_remains_optional():
    data = json.loads(DATA_PATH.read_text())[0]
    data["phone"] = None
    assert Resource.model_validate(data).phone is None
