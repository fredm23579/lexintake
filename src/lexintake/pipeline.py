"""The LexIntake pipeline: five stages over one case workspace.

Workspace layout (created on first run):

    <workspace>/
      lexintake.toml             per-case config (notebook, backend, ...)
      01_mail_in/                drop .eml/.msg/.mbox here (or Stage 1 does)
      02_mail_md/                Stage 2: email.md + attachments/ per message
      03_converted/              Stage 3: hash-named Markdown conversions
      05_artifacts/              Stage 5: chronology, parties, exhibits, privilege
      _audit/                    one JSON record per run (chain of custody)
      .nlm/                      Stage 4 state (manifest DB, uploader state)

Idempotency contract, enforced and tested:

* Stage 2 skips messages already rendered (mail2md hash-named folders).
* Stage 3 converts an attachment only if no output with its content hash
  exists — renaming or re-running never re-converts identical bytes.
* Stage 4 dedupes by nlm's content fingerprint — unchanged files re-upload
  nothing.

Windows hardening on every write path: leaf names sanitized (reserved names,
illegal chars), long paths handled, and attachments locked by Word/Outlook
are *skipped with a warning* this run instead of aborting the batch.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from mail2md.converter import convert as mail2md_convert            # Stage 2
from omniconvert_md.converter import ConversionOptions, MarkdownConverter  # Stage 3
from nlm.config import load_config                                  # Stage 4
from nlm.engine import AddOutcome, SourceManager
from nlm.manifest import Manifest
from nlm.uploaders import build_uploader

from . import artifacts as artifacts_mod
from . import winsafe
from .config import LexConfig

# Formats NotebookLM ingests directly: upload the original bytes untouched.
NATIVE_SOURCE_EXTS = {
    ".pdf", ".txt", ".md", ".markdown", ".rst",
    ".html", ".htm", ".csv", ".tsv", ".json", ".xml",
}
ALREADY_MARKDOWN = {".md", ".markdown"}
# Formats omniconvert lifts to Markdown but NotebookLM cannot read natively.
CONVERTIBLE_EXTS = {
    ".docx", ".doc", ".pptx", ".xlsx", ".rtf", ".epub", ".ipynb",
    ".eml", ".msg", ".yaml", ".yml", ".toml",
    ".png", ".jpg", ".jpeg", ".tiff", ".gif",   # OCR path, opt-in
}
# Converted outputs end in "-<12 hex chars>.md"; matching on the hash (not the
# human stem, which sanitization may rewrite) is what makes skip-detection
# robust. See _converted_exists().
_HASH_SUFFIX = re.compile(r"-([0-9a-f]{12})\.md$")


@dataclass
class StageResult:
    name: str
    ok: bool
    detail: str
    artifacts: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    """Everything one run did; serialized verbatim into _audit/."""

    started: str
    notebook: str
    backend: str
    stages: list[StageResult] = field(default_factory=list)
    emails_markdown: list[str] = field(default_factory=list)
    converted: list[str] = field(default_factory=list)
    skipped_already_md: list[str] = field(default_factory=list)
    skipped_locked: list[str] = field(default_factory=list)
    uploaded: list[str] = field(default_factory=list)
    deduped: list[str] = field(default_factory=list)
    tracked_pending: list[str] = field(default_factory=list)
    artifact_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self, indent=2, default=lambda o: getattr(o, "__dict__", str(o)))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class LexIntakePipeline:
    """Run Stages 2-5 against one workspace. Stage 1 lives in the CLI."""

    def __init__(self, config: LexConfig) -> None:
        self.cfg = config
        ws = config.workspace
        self.mail_in = ws / "01_mail_in"
        self.mail_md = ws / "02_mail_md"
        self.converted_dir = ws / "03_converted"
        self.artifacts_dir = ws / "05_artifacts"
        self.audit_dir = ws / "_audit"
        for d in (self.mail_in, self.mail_md, self.converted_dir, self.audit_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._converter = MarkdownConverter(
            ConversionOptions(
                prefer_markitdown=config.prefer_markitdown,
                ocr=config.ocr,
                include_metadata=True,
                include_report=True,  # omniconvert's per-file audit trail stays in
            )
        )

        # Stage 4 wiring mirrors nlm's own CLI: config -> manifest -> uploader.
        nlm_cfg = load_config(str(ws / ".nlm"))
        nlm_cfg.backend = config.backend
        nlm_cfg.default_notebook = config.notebook
        nlm_cfg.save()
        self._nlm_cfg = nlm_cfg
        self._sources = SourceManager(
            Manifest(nlm_cfg.db_path),
            build_uploader(
                nlm_cfg.backend,
                state_dir=nlm_cfg.state_dir,
                backend_config=nlm_cfg.backend_config,
            ),
        )

    # ---- Stage 2: mail files -> email.md + attachments -------------------
    def stage_mail_to_markdown(self, report: RunReport) -> None:
        try:
            generated = mail2md_convert(self.mail_in, self.mail_md, recursive=True)
        except Exception as exc:
            report.stages.append(StageResult("mail_to_md", False, f"mail2md: {exc}"))
            report.errors.append(f"mail_to_md: {exc}")
            return
        report.emails_markdown = [str(p) for p in generated]
        report.stages.append(
            StageResult(
                "mail_to_md", True,
                f"{len(generated)} message(s) rendered", report.emails_markdown,
            )
        )

    # ---- Stage 3: convert attachments not already Markdown ---------------
    def _iter_attachments(self):
        for att_dir in self.mail_md.glob("*/attachments"):
            for f in sorted(att_dir.iterdir()):
                if f.is_file():
                    yield f

    def _converted_exists(self, digest12: str) -> Path | None:
        """Find a previously converted output by its content-hash suffix.

        Hash matching (not stem matching) so Windows-name sanitization or a
        user rename of the source never causes a duplicate conversion.
        """
        for candidate in self.converted_dir.glob(f"*-{digest12}.md"):
            if _HASH_SUFFIX.search(candidate.name):
                return candidate
        return None

    def stage_convert(self, report: RunReport) -> None:
        done = 0
        for att in self._iter_attachments():
            ext = att.suffix.lower()
            if ext in ALREADY_MARKDOWN:
                report.skipped_already_md.append(str(att))
                continue
            if ext not in CONVERTIBLE_EXTS:
                continue  # natively ingestible: Stage 4 uploads original bytes
            if winsafe.is_locked(att):
                # Word/Outlook still holds the handle: pick it up next run.
                report.skipped_locked.append(str(att))
                continue
            digest12 = _sha256(att)[:12]
            if self._converted_exists(digest12):
                report.skipped_already_md.append(str(att))
                continue
            try:
                result = self._converter.convert(att)
                stem = winsafe.sanitize_component(att.stem.replace(" ", "-"), max_len=80)
                target = winsafe.safe_write_text(
                    self.converted_dir / f"{stem}-{digest12}.md", result.markdown
                )
                report.converted.append(str(target))
                done += 1
            except Exception as exc:
                report.errors.append(f"convert {att.name}: {exc}")
        report.stages.append(
            StageResult(
                "convert", True,
                f"{done} converted · {len(report.skipped_already_md)} already md "
                f"· {len(report.skipped_locked)} locked (deferred)",
                report.converted,
            )
        )

    # ---- Stage 4: upload + manage NotebookLM sources ----------------------
    def _ingestible(self):
        yield from self.mail_md.glob("*/email.md")
        yield from self.converted_dir.glob("*.md")
        for att in self._iter_attachments():
            if att.suffix.lower() in NATIVE_SOURCE_EXTS:
                yield att

    def stage_sources(self, report: RunReport) -> None:
        paths = sorted(set(self._ingestible()))
        for r in self._sources.add_paths(self.cfg.notebook, paths):
            label = str(r.path)
            if r.outcome is AddOutcome.UPLOADED:
                report.uploaded.append(label)
            elif r.outcome is AddOutcome.DUPLICATE:
                report.deduped.append(label)
            elif r.outcome is AddOutcome.TRACKED:
                report.tracked_pending.append(label)
            else:
                report.errors.append(f"upload {label}: {r.message}")
        report.stages.append(
            StageResult(
                "sources", True,
                f"{len(report.uploaded)} uploaded · {len(report.deduped)} deduped "
                f"· {len(report.tracked_pending)} pending",
                report.uploaded,
            )
        )

    # ---- Stage 5: attorney-review artifacts -------------------------------
    def stage_artifacts(self, report: RunReport) -> None:
        if not self.cfg.artifacts:
            report.stages.append(StageResult("artifacts", True, "disabled in config"))
            return
        try:
            files = artifacts_mod.write_artifacts(
                self.mail_md, self.artifacts_dir, case=self.cfg.notebook or "case"
            )
        except Exception as exc:
            report.stages.append(StageResult("artifacts", False, str(exc)))
            report.errors.append(f"artifacts: {exc}")
            return
        report.artifact_files = [str(f) for f in files]
        report.stages.append(
            StageResult(
                "artifacts", True,
                f"{len(files)} artifact(s) written", report.artifact_files,
            )
        )

    # ---- run ---------------------------------------------------------------
    def run(self) -> RunReport:
        report = RunReport(
            started=datetime.now(timezone.utc).isoformat(),
            notebook=self.cfg.notebook,
            backend=self.cfg.backend,
        )
        self.stage_mail_to_markdown(report)
        self.stage_convert(report)
        self.stage_sources(report)
        self.stage_artifacts(report)
        audit = self.audit_dir / (
            f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        audit.write_text(report.to_json(), encoding="utf-8")
        report.stages.append(StageResult("audit", True, str(audit), [str(audit)]))
        return report
