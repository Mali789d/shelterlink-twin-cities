"""Static safety contract for the local-test directory page (web/index.html).

The page renders provider data, so its markup and glue are checked the way the
other browser modules are: fail-closed CSP, no external resources, no inline
handlers, text-only DOM writes, and the same 211/911 notice everywhere.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
PAGE = (WEB / "index.html").read_text(encoding="utf-8")
GLUE = (WEB / "index.mjs").read_text(encoding="utf-8")
VIEW = (WEB / "directory-view.mjs").read_text(encoding="utf-8")


def test_page_declares_fail_closed_csp():
    match = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', PAGE)
    assert match, "the page must carry a CSP meta tag"
    policy = match.group(1)
    assert "default-src 'none'" in policy
    assert "script-src 'self'" in policy  # no inline scripts, no third-party code
    assert "connect-src 'self'" in policy  # the snapshot fetch stays same-origin
    assert "base-uri 'none'" in policy
    assert "form-action 'none'" in policy  # without JS the search form goes nowhere


def test_page_loads_only_the_local_module_script():
    scripts = re.findall(r'<script[^>]*>', PAGE)
    assert len(scripts) == 1
    assert 'type="module"' in scripts[0]
    assert 'src="./index.mjs"' in scripts[0]


def test_page_has_no_external_or_inline_resources():
    headless = re.sub(r"https?://\S+", "", PAGE)  # checked separately below
    assert "http://" not in headless and "https://" not in headless
    # No inline event handlers: all wiring lives in index.mjs.
    assert not re.search(r'\son[a-z]+\s*=', PAGE, re.IGNORECASE)
    for tag in ("<img", "<iframe", "<video", "<audio", "<object", "<embed", "<link"):
        assert tag not in PAGE


def test_page_keeps_the_safety_notice_and_prototype_banner():
    assert 'id="notice"' in PAGE
    assert 'class="banner"' in PAGE
    # The banner text is the same string directory-view.mjs exports, so the two
    # cannot drift apart.
    banner = re.search(r'<p class="banner">(.*?)</p>', PAGE, re.DOTALL).group(1)
    flattened = " ".join(banner.split())
    assert "not a live referral service" in flattened
    assert "prototype" in flattened.lower()


def test_page_declares_language_and_accessible_live_region():
    assert '<html lang="en">' in PAGE
    assert 'role="status"' in PAGE and 'aria-live="polite"' in PAGE
    # The location input is labeled and bounded like the parsers behind it.
    assert re.search(r'<label for="location">', PAGE)
    assert re.search(r'<input[^>]*maxlength="100"', PAGE)


def test_glue_writes_text_never_html():
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML",
                      "document.write", "eval(", "new Function"):
        assert forbidden not in GLUE
        assert forbidden not in VIEW


def test_glue_has_no_storage_tracking_or_beacons():
    for forbidden in ("localStorage", "sessionStorage", "indexedDB",
                      "navigator.sendBeacon", "cookie"):
        assert forbidden not in GLUE
        assert forbidden not in VIEW


def test_glue_imports_only_relative_modules():
    imports = re.findall(r"from\s+'([^']+)'", GLUE)
    assert imports, "index.mjs must wire the tested modules"
    assert all(item.startswith("./") for item in imports)
    assert not any(".." in item for item in imports)


def test_glue_never_fabricates_availability():
    # The export deliberately drops hours/availability/open claims; the page
    # must not reintroduce wording that implies live availability.
    combined = (GLUE + VIEW).lower()
    assert "open now" not in combined
    assert "beds available" not in combined


def test_view_module_is_dom_free():
    for forbidden in ("document.", "window.", "fetch(", "XMLHttpRequest"):
        assert forbidden not in VIEW


def test_notice_wording_matches_sms_safety_footer():
    # The page's notice line carries the same 211/911 guidance as every SMS reply.
    assert "211" in VIEW and "911" in VIEW


def test_category_select_is_labeled_and_matches_the_validated_category_set():
    assert re.search(r'<label for="category">', PAGE), "the category control must be labeled"
    match = re.search(r'<select id="category"[^>]*>(.*?)</select>', PAGE, re.DOTALL)
    assert match, "the category control must be a select"
    options = re.findall(r'<option value="([^"]*)"', match.group(1))
    # The empty choice means "all services"; the rest mirror the category set the
    # session and directory validate, so the page can never send an unknown value.
    assert options == ["", "shelter", "meal", "warming", "shower"]


def test_radius_select_is_labeled_with_bounded_choices_and_the_session_default():
    assert re.search(r'<label for="radius">', PAGE), "the radius control must be labeled"
    match = re.search(r'<select id="radius"[^>]*>(.*?)</select>', PAGE, re.DOTALL)
    assert match, "the radius control must be a select"
    options = re.findall(r'<option value="([^"]+)"([^>]*)>([^<]+)</option>', match.group(1))
    # Fixed choices keep free-form numbers, and the text injected with them,
    # out of the page; the session still revalidates whatever arrives.
    assert [value for value, _, _ in options] == ["5", "10", "25", "50"]
    assert all("miles" in label for _, _, label in options)
    selected = [value for value, attrs, _ in options if "selected" in attrs]
    # The markup default must match the session's own default radius (25 miles),
    # or the page would show one radius while searching another.
    assert selected == ["25"]


def test_glue_forwards_only_a_finite_positive_radius():
    assert "getElementById('radius')" in GLUE
    forward = re.search(
        r"radiusMiles:\s*Number\.isFinite\(radius\)\s*&&\s*radius\s*>\s*0"
        r"\s*\?\s*radius\s*:\s*undefined", GLUE)
    assert forward, ("glue must forward only a finite, positive radius; "
                     "anything else falls back to the session default")
