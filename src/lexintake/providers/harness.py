"""Shared Playwright browser executor for the OpenAI/Anthropic adapters.

Each provider loop only knows "perform this named action, then screenshot";
this class owns the single mapping from model action vocabulary to Playwright
calls. Gemini does not use this harness — its export path is mail2md's own
hardened agent (host allow-lists, human confirmation gates), which we reuse
rather than re-implement.

The action vocabularies differ slightly between providers (OpenAI:
``click/double_click/scroll/type/keypress/wait``; Anthropic: ``left_click/
type/key/scroll/screenshot``...), so :meth:`perform` normalizes both into one
switch. Unknown actions are ignored with a log line rather than crashing a
half-finished export.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

log = logging.getLogger("lexintake.harness")

# provider action name -> canonical action
_ALIASES = {
    "click": "click", "left_click": "click",                 # OpenAI / Anthropic
    "double_click": "double_click", "right_click": "right_click",
    "keypress": "key", "key": "key",
    "type": "type", "scroll": "scroll", "wait": "wait",
    "screenshot": "noop", "cursor_position": "noop", "move": "noop",
    "mouse_move": "noop",
}


class BrowserExecutor:
    """Maps canonical computer-use actions onto one Playwright page."""

    def __init__(self, page: Any) -> None:
        self.page = page

    def url(self) -> str:
        return self.page.url

    def screenshot_png(self) -> bytes:
        return self.page.screenshot(type="png")

    def screenshot_b64(self) -> str:
        return base64.b64encode(self.screenshot_png()).decode("ascii")

    def perform(self, action: str, args: dict[str, Any]) -> None:
        kind = _ALIASES.get(action)
        if kind is None:
            log.warning("ignoring unknown computer action %r", action)
            return
        if kind == "noop":
            return
        if kind in ("click", "double_click", "right_click"):
            x, y = self._coords(args)
            clicks = 2 if kind == "double_click" else 1
            button = "right" if kind == "right_click" else "left"
            self.page.mouse.click(x, y, click_count=clicks, button=button)
        elif kind == "type":
            self.page.keyboard.type(args.get("text", ""))
        elif kind == "key":
            # OpenAI sends a list under "keys"; Anthropic a "+"-joined string.
            keys = args.get("keys") or str(args.get("text", "")).split("+")
            for key in keys:
                self.page.keyboard.press(_normalize_key(key))
        elif kind == "scroll":
            x, y = self._coords(args)
            self.page.mouse.move(x, y)
            self.page.mouse.wheel(
                args.get("scroll_x", 0) or 0, args.get("scroll_y", 0) or 0
            )
        elif kind == "wait":
            self.page.wait_for_timeout(int(args.get("ms", 1000)))

    @staticmethod
    def _coords(args: dict[str, Any]) -> tuple[int, int]:
        # Anthropic nests under "coordinate": [x, y]; OpenAI uses flat x/y.
        if "coordinate" in args and args["coordinate"]:
            x, y = args["coordinate"][:2]
            return int(x), int(y)
        return int(args.get("x", 0)), int(args.get("y", 0))


_KEY_MAP = {
    "return": "Enter", "enter": "Enter", "tab": "Tab", "esc": "Escape",
    "escape": "Escape", "space": " ", "ctrl": "Control", "cmd": "Meta",
    "alt": "Alt", "shift": "Shift", "backspace": "Backspace",
    "delete": "Delete", "pageup": "PageUp", "pagedown": "PageDown",
}


def _normalize_key(key: str) -> str:
    return _KEY_MAP.get(key.strip().lower(), key.strip())
