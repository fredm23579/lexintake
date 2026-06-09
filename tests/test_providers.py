import pytest

from lexintake.providers import available_providers, get_capability
from lexintake.providers import anthropic_cua, openai_cua
from lexintake.providers.harness import BrowserExecutor


def test_capability_report_covers_all_providers():
    names = {c.provider for c in available_providers()}
    assert names == {"gemini", "openai", "anthropic"}


def test_capability_gemini_sdk_detected(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cap = get_capability("gemini")
    assert cap.sdk_installed is True          # mail2md is installed in the venv
    assert cap.ready is False                 # but no key in the test env
    assert "GEMINI_API_KEY" in cap.explain()


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="unknown provider"):
        get_capability("copilot")


def test_openai_request_shape():
    req = openai_cua.build_initial_request("export mail")
    assert req["tools"][0]["type"] == "computer_use_preview"
    assert req["tools"][0]["environment"] == "browser"
    assert req["truncation"] == "auto"
    reply = openai_cua.build_screenshot_reply("call_1", "QUJD", current_url="https://mail.google.com")
    assert reply["output"]["image_url"].startswith("data:image/png;base64,QUJD")
    assert reply["output"]["current_url"] == "https://mail.google.com"


def test_anthropic_request_shape():
    req = anthropic_cua.build_initial_request("export mail")
    tool = req["tools"][0]
    assert tool["type"] == "computer_20251124" and tool["name"] == "computer"
    assert anthropic_cua.COMPUTER_USE_BETA in req["betas"]
    result = anthropic_cua.build_tool_result("toolu_1", b"PNG")
    assert result["tool_use_id"] == "toolu_1"
    assert result["content"][0]["source"]["media_type"] == "image/png"


class FakePage:
    """Records the Playwright calls the executor makes."""

    def __init__(self):
        self.calls = []
        self.url = "about:blank"
        self.mouse = self
        self.keyboard = self

    def click(self, x, y, click_count=1, button="left"):
        self.calls.append(("click", x, y, click_count, button))

    def type(self, text):
        self.calls.append(("type", text))

    def press(self, key):
        self.calls.append(("press", key))

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def wheel(self, dx, dy):
        self.calls.append(("wheel", dx, dy))

    def wait_for_timeout(self, ms):
        self.calls.append(("wait", ms))


def test_harness_maps_both_action_vocabularies():
    page = FakePage()
    ex = BrowserExecutor(page)
    ex.perform("left_click", {"coordinate": [10, 20]})          # Anthropic style
    ex.perform("click", {"x": 30, "y": 40})                     # OpenAI style
    ex.perform("keypress", {"keys": ["ctrl", "Return"]})        # OpenAI keys list
    ex.perform("key", {"text": "ctrl+s"})                       # Anthropic combo
    ex.perform("scroll", {"x": 0, "y": 0, "scroll_y": 120})
    ex.perform("definitely_not_an_action", {})                  # ignored, no crash
    assert ("click", 10, 20, 1, "left") in page.calls
    assert ("click", 30, 40, 1, "left") in page.calls
    assert ("press", "Control") in page.calls and ("press", "Enter") in page.calls
    assert ("press", "s") in page.calls
    assert ("wheel", 0, 120) in page.calls
