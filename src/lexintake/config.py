"""Workspace configuration: a single ``lexintake.toml`` per case workspace.

Attorneys set the notebook id, backend, and provider once; every later
``lexintake run`` picks them up without flags. Reads use stdlib ``tomllib``;
writes use a deliberately tiny TOML emitter so the package adds no config
dependency. Only the flat key/value subset LexIntake itself writes is
supported by the emitter — that is all it ever needs to round-trip.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

CONFIG_NAME = "lexintake.toml"


@dataclass
class LexConfig:
    """Per-workspace settings, persisted next to the case files."""

    notebook: str = ""
    backend: str = "stub"            # stub | enterprise
    provider: str = "gemini"         # gemini | openai | anthropic  (Stage 1 only)
    mail_provider: str = "gmail"     # gmail | outlook
    ocr: bool = False                # OCR image attachments (needs tesseract)
    prefer_markitdown: bool = False  # try MarkItDown before native handlers
    max_messages: int = 25           # browser-export cap per run
    artifacts: bool = True           # generate Stage 5 attorney artifacts
    workspace: Path = field(default_factory=Path.cwd)

    @classmethod
    def load(cls, workspace: Path) -> "LexConfig":
        """Load ``lexintake.toml`` from *workspace*; defaults if absent."""
        cfg = cls(workspace=Path(workspace).resolve())
        path = cfg.workspace / CONFIG_NAME
        if not path.is_file():
            return cfg
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        valid = {f.name for f in fields(cls)} - {"workspace"}
        for key, value in data.get("lexintake", data).items():
            if key in valid:
                setattr(cfg, key, value)
        return cfg

    def save(self) -> Path:
        """Write the config back as a flat ``[lexintake]`` table."""
        path = self.workspace / CONFIG_NAME
        lines = ["[lexintake]"]
        for f in fields(self):
            if f.name == "workspace":
                continue  # implicit: the directory the file lives in
            lines.append(f"{f.name} = {_toml_value(getattr(self, f.name))}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


def _toml_value(value: object) -> str:
    """Emit one TOML scalar. Strings are escaped; bools are lowercase."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
