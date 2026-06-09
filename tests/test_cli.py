from pathlib import Path

from lexintake.cli import main
from lexintake.config import CONFIG_NAME, LexConfig


def test_init_creates_config_and_inbox(tmp_path: Path, capsys):
    assert main(["init", str(tmp_path), "--notebook", "NB-1"]) == 0
    assert (tmp_path / CONFIG_NAME).is_file()
    assert (tmp_path / "01_mail_in").is_dir()
    assert LexConfig.load(tmp_path).notebook == "NB-1"


def test_run_requires_notebook(tmp_path: Path, capsys):
    assert main(["run", str(tmp_path)]) == 2
    assert "no notebook" in capsys.readouterr().err


def test_run_end_to_end(workspace: Path, capsys):
    main(["init", str(workspace), "--notebook", "NB-CLI"])
    assert main(["run", str(workspace)]) == 0
    out = capsys.readouterr().out
    assert "uploaded: 6" in out and "errors: 0" in out


def test_status_after_run(workspace: Path, capsys):
    main(["init", str(workspace), "--notebook", "NB-CLI"])
    main(["run", str(workspace)])
    assert main(["status", str(workspace)]) == 0
    out = capsys.readouterr().out
    assert "6 tracked source(s)" in out
    assert "last run: run-" in out


def test_doctor_reports_providers(tmp_path: Path, capsys):
    assert main(["doctor", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "gemini" in out and "openai" in out and "anthropic" in out


def test_export_dry_run_is_safe(workspace: Path, capsys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # capability gate passes
    main(["init", str(workspace), "--notebook", "NB-CLI"])
    assert main(["export", str(workspace), "--query", "label:lucerne"]) == 0
    assert "DRY RUN" in capsys.readouterr().out
