"""Anthropic computer-use adapter (``computer_20251124`` tool, beta header).

Same shape as the OpenAI adapter: pure request builders (offline-testable)
plus a gated live loop that maps tool_use blocks onto the shared browser
executor. The agentic loop is ours to run — Anthropic's computer-use tool is
schema-less on the client side; we declare the tool, the model emits
``tool_use`` blocks with actions like ``screenshot``, ``left_click``,
``type``, and we answer with ``tool_result`` blocks containing images.
"""

from __future__ import annotations

import base64
from typing import Any

ANTHROPIC_CUA_MODEL = "claude-opus-4-8"
COMPUTER_USE_BETA = "computer-use-2025-11-24"
DISPLAY = (1280, 800)


def build_tool_spec(width: int = DISPLAY[0], height: int = DISPLAY[1]) -> dict[str, Any]:
    return {
        "type": "computer_20251124",
        "name": "computer",
        "display_width_px": width,
        "display_height_px": height,
    }


def build_initial_request(task: str, *, model: str = ANTHROPIC_CUA_MODEL) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": 4096,
        "tools": [build_tool_spec()],
        "betas": [COMPUTER_USE_BETA],
        "messages": [{"role": "user", "content": task}],
    }


def build_tool_result(tool_use_id: str, screenshot_png: bytes) -> dict[str, Any]:
    """A ``tool_result`` content block answering one computer action."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(screenshot_png).decode("ascii"),
                },
            }
        ],
    }


def extract_tool_uses(message: Any) -> list[Any]:
    return [b for b in message.content if getattr(b, "type", None) == "tool_use"]


def run_export_anthropic(task: str, executor, *, max_steps: int = 80) -> int:
    """Drive a browser export with Anthropic computer use; returns steps taken."""
    from anthropic import Anthropic  # gated import: only on live export

    client = Anthropic()
    request = build_initial_request(task)
    messages = request["messages"]
    steps = 0
    while steps < max_steps:
        response = client.beta.messages.create(**{**request, "messages": messages})
        tool_uses = extract_tool_uses(response)
        if not tool_uses or response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in tool_uses:
            action = block.input.get("action", "screenshot")
            executor.perform(action, block.input)
            results.append(build_tool_result(block.id, executor.screenshot_png()))
        messages.append({"role": "user", "content": results})
        steps += 1
    return steps
