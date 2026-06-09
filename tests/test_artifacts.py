from pathlib import Path

from lexintake import artifacts


EMAIL_MD = """\
---
title: "RE: Lucerne settlement"
from: "Paula Counsel <paula@firmlaw.com>"
to: "fred@client.example"
date: "Tue, 14 Apr 2026 09:30:00 -0700"
message_id: "<m1@firmlaw.com>"
content_sha256: "abc123"
---

# Body

Attorney-client privileged. Do not forward.

| [memo.docx](attachments/memo.docx) | `application/msword` | 1234 | `deadbeefcafe` |
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    d = tmp_path / "02_mail_md" / name
    d.mkdir(parents=True)
    p = d / "email.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_email_md(tmp_path: Path):
    rec = artifacts.parse_email_md(_write(tmp_path, "m1", EMAIL_MD))
    assert rec.subject == "RE: Lucerne settlement"
    assert rec.date and rec.date.year == 2026 and rec.date.month == 4
    assert rec.attachments == [("memo.docx", "application/msword", "deadbeefcafe")]
    assert "privileg" in "".join(rec.privileged_hits)


def test_undated_sorts_last(tmp_path: Path):
    _write(tmp_path, "dated", EMAIL_MD)
    _write(tmp_path, "undated", EMAIL_MD.replace(
        'date: "Tue, 14 Apr 2026 09:30:00 -0700"', 'date: ""'))
    records = artifacts.collect_records(tmp_path / "02_mail_md")
    assert records[0].date is not None and records[-1].date is None


def test_write_artifacts_full_set(tmp_path: Path):
    _write(tmp_path, "m1", EMAIL_MD)
    out = artifacts.write_artifacts(
        tmp_path / "02_mail_md", tmp_path / "05_artifacts", case="X-1"
    )
    names = {p.name for p in out}
    assert names == {
        "chronology.md", "parties.md", "exhibit_index.md", "privilege_review.md"
    }
    chrono = (tmp_path / "05_artifacts" / "chronology.md").read_text()
    assert "2026-04-14" in chrono and "verify before filing" in chrono
    parties = (tmp_path / "05_artifacts" / "parties.md").read_text()
    assert "paula@firmlaw.com" in parties and "fred@client.example" in parties
    privilege = (tmp_path / "05_artifacts" / "privilege_review.md").read_text()
    assert "Flagged: **1** of 1" in privilege
    exhibits = (tmp_path / "05_artifacts" / "exhibit_index.md").read_text()
    assert "deadbeefcafe" in exhibits


def test_privilege_screen_no_false_positive(tmp_path: Path):
    clean = EMAIL_MD.replace("Attorney-client privileged. Do not forward.",
                             "See you at the hearing.")
    rec = artifacts.parse_email_md(_write(tmp_path, "clean", clean))
    assert rec.privileged_hits == []
