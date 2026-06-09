"""LexIntake — legal email intake pipeline for Windows.

One workflow over three independent projects:

  Stage 1  EXPORT     mail2md-computer-use   policy-gated browser export of mail
  Stage 2  MAIL->MD   mail2md-computer-use   deterministic email.md + attachments
  Stage 3  CONVERT    omniconvert-md         convert attachments not already Markdown
  Stage 4  SOURCES    notebooklm-manager     fingerprint, dedupe, upload, track
  Stage 5  ARTIFACTS  lexintake              chronology, parties, exhibit index

Every stage is idempotent: re-running a workspace never re-converts or
re-uploads unchanged content, and every run leaves a JSON audit record.
"""

from __future__ import annotations

__version__ = "1.0.0"
