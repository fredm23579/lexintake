# Changelog

## 1.0.0 — 2026-06-09

Initial release.

* Five-stage pipeline: browser export (optional) → mail-to-Markdown →
  convert-if-not-already → deduped NotebookLM sources → attorney artifacts.
* Stage engines: mail2md-computer-use, omniconvert-md, notebooklm-manager,
  called through their real public APIs (no shelling out).
* Attorney artifacts: chronology, parties index, exhibit index with SHA-256,
  privilege-review queue (keyword screen).
* Windows hardening: long paths, reserved/illegal names, locked-file
  deferral, OneDrive/UNC detection, legal-product folder discovery.
* Computer-use providers: Gemini (via mail2md's hardened agent), OpenAI
  Responses `computer_use_preview`, Anthropic `computer_20251124`; shared
  Playwright executor; explicit capability gating in `doctor`.
* Per-case TOML config, JSON audit record per run, 36 offline tests,
  Windows+Linux CI matrix, one-line PowerShell installer, folder watcher,
  n8n example workflow.
