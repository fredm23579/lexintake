"""Gemini provider: delegate Stage 1 to mail2md's own browser agent.

mail2md-computer-use already ships a policy-gated Gemini computer-use loop —
host allow-lists per mail provider, human confirmation for sensitive actions,
bounded steps. Re-implementing that here would only add risk, so this module
is a thin translation from LexIntake's config to mail2md's ``ExportRequest``.
"""

from __future__ import annotations

from pathlib import Path


def run_export_gemini(
    *,
    mail_provider: str,
    query: str,
    download_dir: Path,
    profile_dir: Path,
    max_messages: int,
) -> list[Path]:
    """Run mail2md's browser export; returns the downloaded mail files."""
    # Gated import: pulls playwright + google-genai, neither needed offline.
    from mail2md.browser_agent import ExportRequest, run_export

    request = ExportRequest(
        provider=mail_provider,
        query=query,
        download_dir=Path(download_dir).resolve(),
        profile_dir=Path(profile_dir).resolve(),
        max_messages=max_messages,
    )
    return run_export(request)
