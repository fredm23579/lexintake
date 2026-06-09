"""End-to-end pipeline guarantees, offline against the stub backend:

convert-if-not-already, content-hash skip (rename-proof), idempotent dedup,
locked-file deferral, Windows-name sanitization, audit trail.
"""

from __future__ import annotations

import json
from pathlib import Path

from lexintake import winsafe


def test_full_run_converts_uploads_artifacts(pipeline):
    report = pipeline.run()
    assert report.errors == []
    assert len(report.emails_markdown) == 2
    # Exactly the .docx converts; notes.md is already Markdown.
    assert len(report.converted) == 1
    assert report.converted[0].endswith(".md")
    assert any(p.endswith("notes.md") for p in report.skipped_already_md)
    # 2 email.md + 1 converted + notes.md + damages.csv + sample's native att.
    assert len(report.uploaded) == 6
    assert len(report.artifact_files) == 4


def test_windows_illegal_attachment_name_sanitized(pipeline):
    pipeline.run()
    (converted,) = list(pipeline.converted_dir.glob("*.md"))
    assert not set('<>:"|?*') & set(converted.name)


def test_second_run_fully_idempotent(pipeline):
    pipeline.run()
    report2 = pipeline.run()
    assert report2.converted == []
    assert report2.uploaded == []
    assert len(report2.deduped) == 6
    assert report2.errors == []


def test_converted_skip_survives_rename(pipeline):
    """Hash-suffix matching: renaming the converted file's stem must not
    trigger a re-conversion (the regression behind filename-prefix matching)."""
    pipeline.run()
    (converted,) = list(pipeline.converted_dir.glob("*.md"))
    digest12 = converted.name.rsplit("-", 1)[1].removesuffix(".md")
    converted.rename(converted.with_name(f"Totally-Different-Stem-{digest12}.md"))
    report2 = pipeline.run()
    assert report2.converted == []


def test_locked_attachment_deferred_not_fatal(pipeline, monkeypatch):
    """A Word-locked .docx is skipped this run and converted next run."""
    real_is_locked = winsafe.is_locked

    def fake_is_locked(path: Path) -> bool:
        return path.suffix == ".docx" or real_is_locked(path)

    monkeypatch.setattr("lexintake.pipeline.winsafe.is_locked", fake_is_locked)
    report = pipeline.run()
    assert report.errors == []
    assert len(report.skipped_locked) == 1
    assert report.converted == []

    monkeypatch.undo()
    report2 = pipeline.run()           # handle released: converts now
    assert len(report2.converted) == 1
    assert report2.skipped_locked == []


def test_audit_record_written_and_parseable(pipeline):
    report = pipeline.run()
    audits = sorted(pipeline.audit_dir.glob("run-*.json"))
    assert audits
    data = json.loads(audits[-1].read_text(encoding="utf-8"))
    assert data["notebook"] == "TEST-NB"
    assert data["uploaded"] == report.uploaded


def test_converted_markdown_keeps_conversion_report(pipeline):
    """omniconvert's embedded Conversion Report (chain of custody) survives."""
    pipeline.run()
    (converted,) = list(pipeline.converted_dir.glob("*.md"))
    text = converted.read_text(encoding="utf-8")
    assert "Settlement Memorandum" in text
    assert "Conversion Report" in text
