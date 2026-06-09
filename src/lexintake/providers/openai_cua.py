"""OpenAI computer-use adapter (Responses API, ``computer_use_preview``).

The request builders are pure functions so the exact payloads sent to the
API are unit-testable offline. The live loop is import-gated: nothing here
touches the network unless :func:`run_export_openai` is actually called with
a ready capability.

Spec (verified against the OpenAI Responses API, 2026): the tool is declared
as ``{"type": "computer_use_preview", "display_width": ..., "display_height":
..., "environment": "browser"}``; the model returns ``computer_call`` items
whose actions we execute and answer with ``computer_call_output`` items
carrying a fresh screenshot.
"""

from __future__ import annotations

from typing import Any

OPENAI_CUA_MODEL = "computer-use-preview"
DISPLAY = (1280, 800)


def build_tool_spec(width: int = DISPLAY[0], height: int = DISPLAY[1]) -> dict[str, Any]:
    return {
        "type": "computer_use_preview",
        "display_width": width,
        "display_height": height,
        "environment": "browser",
    }


def build_initial_request(task: str, *, model: str = OPENAI_CUA_MODEL) -> dict[str, Any]:
    """First Responses-API call: task instructions + the computer tool."""
    return {
        "model": model,
        "tools": [build_tool_spec()],
        "input": [{"role": "user", "content": [{"type": "input_text", "text": task}]}],
        "truncation": "auto",
        "reasoning": {"summary": "concise"},
    }


def build_screenshot_reply(
    call_id: str, screenshot_b64: str, *, current_url: str | None = None
) -> dict[str, Any]:
    """Answer a ``computer_call`` with the post-action screenshot."""
    output: dict[str, Any] = {
        "type": "computer_call_output",
        "call_id": call_id,
        "output": {
            "type": "computer_screenshot",
            "image_url": f"data:image/png;base64,{screenshot_b64}",
        },
    }
    if current_url:
        # Lets the API run its own URL safety checks against the live page.
        output["output"]["current_url"] = current_url
    return output


def extract_computer_calls(response: Any) -> list[Any]:
    """The pending ``computer_call`` items from a Responses API response."""
    return [item for item in response.output if item.type == "computer_call"]


def run_export_openai(task: str, executor, *, max_steps: int = 80) -> int:
    """Drive a browser export with OpenAI computer use.

    *executor* is a :class:`lexintake.providers.harness.BrowserExecutor`;
    keeping the SDK loop and the browser side decoupled means this function
    holds zero Playwright knowledge. Returns the number of model steps taken.
    """
    from openai import OpenAI  # gated import: only on live export

    client = OpenAI()
    response = client.responses.create(**build_initial_request(task))
    steps = 0
    while steps < max_steps:
        calls = extract_computer_calls(response)
        if not calls:
            break  # model is done (or asked a question; surfaced via output text)
        call = calls[0]
        executor.perform(call.action.type, vars(call.action))
        shot = executor.screenshot_b64()
        response = client.responses.create(
            model=OPENAI_CUA_MODEL,
            previous_response_id=response.id,
            tools=[build_tool_spec()],
            input=[build_screenshot_reply(call.call_id, shot, current_url=executor.url())],
            truncation="auto",
        )
        steps += 1
    return steps
