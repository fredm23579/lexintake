from pathlib import Path

import tomllib

from lexintake.config import CONFIG_NAME, LexConfig


def test_defaults(tmp_path: Path):
    cfg = LexConfig.load(tmp_path)
    assert cfg.backend == "stub"
    assert cfg.provider == "gemini"
    assert cfg.artifacts is True
    assert cfg.workspace == tmp_path.resolve()


def test_save_load_roundtrip(tmp_path: Path):
    cfg = LexConfig(notebook="CASE-1", backend="enterprise", ocr=True,
                    max_messages=5, workspace=tmp_path)
    cfg.save()
    again = LexConfig.load(tmp_path)
    assert (again.notebook, again.backend, again.ocr, again.max_messages) == (
        "CASE-1", "enterprise", True, 5
    )


def test_emitted_toml_is_valid_and_escaped(tmp_path: Path):
    cfg = LexConfig(notebook='quote " and \\ slash', workspace=tmp_path)
    path = cfg.save()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["lexintake"]["notebook"] == 'quote " and \\ slash'


def test_unknown_keys_ignored(tmp_path: Path):
    (tmp_path / CONFIG_NAME).write_text(
        '[lexintake]\nnotebook = "X"\nbogus = "ignored"\nworkspace = "/evil"\n'
    )
    cfg = LexConfig.load(tmp_path)
    assert cfg.notebook == "X"
    # workspace is never read from the file: it is where the file lives.
    assert cfg.workspace == tmp_path.resolve()
