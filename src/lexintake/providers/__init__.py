"""Computer-use providers for Stage 1 (browser mail export).

Three interchangeable backends drive the export browser session:

* ``gemini``    — delegates to mail2md's proven, policy-gated agent loop.
* ``openai``    — OpenAI Responses API ``computer_use_preview`` tool.
* ``anthropic`` — Anthropic ``computer_20251124`` tool (beta header).

Capability detection is explicit: :func:`available_providers` reports, per
provider, whether its SDK is importable and its API key is set, so the CLI
``doctor`` command tells the attorney exactly what is missing instead of
failing mid-export.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass

#: provider name -> (pip distribution, importable module, API-key env var)
PROVIDERS: dict[str, tuple[str, str, str]] = {
    "gemini": ("mail2md-computer-use", "mail2md.browser_agent", "GEMINI_API_KEY"),
    "openai": ("openai", "openai", "OPENAI_API_KEY"),
    "anthropic": ("anthropic", "anthropic", "ANTHROPIC_API_KEY"),
}


@dataclass(frozen=True)
class Capability:
    provider: str
    sdk_installed: bool
    key_set: bool

    @property
    def ready(self) -> bool:
        return self.sdk_installed and self.key_set

    def explain(self) -> str:
        if self.ready:
            return "ready"
        missing = []
        if not self.sdk_installed:
            missing.append(f"pip install {PROVIDERS[self.provider][0]}")
        if not self.key_set:
            missing.append(f"set {PROVIDERS[self.provider][2]}")
        return "; ".join(missing)


def available_providers() -> list[Capability]:
    """Capability report for every provider, cheap enough to run in doctor."""
    out = []
    for name, (_dist, module, env) in PROVIDERS.items():
        top = module.split(".")[0]
        installed = importlib.util.find_spec(top) is not None
        out.append(Capability(name, installed, bool(os.environ.get(env))))
    return out


def get_capability(provider: str) -> Capability:
    for cap in available_providers():
        if cap.provider == provider:
            return cap
    raise ValueError(f"unknown provider {provider!r}; choose from {sorted(PROVIDERS)}")
