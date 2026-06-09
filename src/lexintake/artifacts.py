"""Stage 5: attorney-review artifacts generated from the processed mailbox.

Inputs are the deterministic ``email.md`` files mail2md writes (YAML
front-matter: title/from/to/cc/date/message_id/content_sha256/...) plus each
email's attachments table. Outputs land in ``05_artifacts/``:

* ``chronology.md``       — every email in date order, linked to its file
* ``parties.md``          — every address seen, with first/last appearance
* ``exhibit_index.md``    — every attachment with SHA-256, ready for exhibit
                            stamping and chain-of-custody citation
* ``privilege_review.md`` — emails whose text trips privilege keywords,
                            queued for attorney eyes FIRST

These are review *accelerators*, not legal conclusions: the privilege screen
is a keyword net to order the review queue, never a basis to produce.
Parsing is a small hand-rolled front-matter reader (the upstream emitter is
deterministic, so a YAML dependency would be dead weight).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

# Conservative privilege net: common privilege markers + counsel vocabulary.
PRIVILEGE_PATTERNS = re.compile(
    r"privileg|attorney[- ]client|work[- ]product|legal advice|"
    r"attorney[- ]work|do not (?:forward|produce)|confidential.{0,20}counsel",
    re.IGNORECASE,
)

_ADDR = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass
class EmailRecord:
    """One parsed email.md: enough metadata to index, sort, and cite."""

    path: Path
    subject: str = "(no subject)"
    sender: str = ""
    recipients: str = ""
    date_raw: str = ""
    message_id: str = ""
    sha256: str = ""
    date: datetime | None = None
    attachments: list[tuple[str, str, str]] = field(default_factory=list)
    # ^ (filename, content_type, sha256) rows from mail2md's attachment table
    privileged_hits: list[str] = field(default_factory=list)


def _front_matter(text: str) -> dict[str, str]:
    """Parse the flat ``key: value`` front-matter block mail2md emits."""
    if not text.startswith("---"):
        return {}
    body = text.split("---", 2)
    if len(body) < 3:
        return {}
    out: dict[str, str] = {}
    for line in body[1].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def parse_email_md(path: Path) -> EmailRecord:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm = _front_matter(text)
    rec = EmailRecord(
        path=path,
        subject=fm.get("title") or "(no subject)",
        sender=fm.get("from", ""),
        recipients=fm.get("to", ""),
        date_raw=fm.get("date", ""),
        message_id=fm.get("message_id", ""),
        sha256=fm.get("content_sha256", ""),
    )
    if rec.date_raw:
        try:  # RFC 2822 first (what mail headers carry), ISO as fallback
            rec.date = parsedate_to_datetime(rec.date_raw)
        except (TypeError, ValueError):
            try:
                rec.date = datetime.fromisoformat(rec.date_raw)
            except ValueError:
                rec.date = None
    # Attachment table rows: | [name](attachments/name) | `type` | size | `sha` |
    for m in re.finditer(
        r"^\|\s*\[([^]]+)\]\([^)]+\)\s*\|\s*`([^`]*)`\s*\|\s*\d+\s*\|\s*`([0-9a-f]+)`",
        text,
        re.MULTILINE,
    ):
        rec.attachments.append((m.group(1), m.group(2), m.group(3)))
    rec.privileged_hits = sorted(
        {m.group(0).lower() for m in PRIVILEGE_PATTERNS.finditer(text)}
    )
    return rec


def collect_records(mail_md_root: Path) -> list[EmailRecord]:
    """Parse every email.md under the Stage 2 output tree, date-sorted."""
    records = [parse_email_md(p) for p in sorted(mail_md_root.glob("*/email.md"))]
    # Undated mail sorts last, original order preserved (stable sort).
    records.sort(key=lambda r: (r.date is None, r.date or datetime.max))
    return records


def _rel(target: Path, base: Path) -> str:
    try:
        return target.relative_to(base).as_posix()
    except ValueError:
        return target.as_posix()


def write_artifacts(mail_md_root: Path, out_dir: Path, *, case: str) -> list[Path]:
    """Generate all Stage 5 artifacts; returns the files written."""
    records = collect_records(mail_md_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir.parent
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    written: list[Path] = []

    # -- chronology --------------------------------------------------------
    lines = [
        f"# Chronology — {case}",
        f"_Generated {stamp} · {len(records)} message(s) · machine-built, verify before filing_",
        "",
        "| Date | From | Subject | Attachments | Source |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        when = r.date.strftime("%Y-%m-%d %H:%M") if r.date else "(undated)"
        lines.append(
            f"| {when} | {r.sender} | {r.subject} | {len(r.attachments)} "
            f"| [{r.path.parent.name}]({_rel(r.path, base)}) |"
        )
    written.append(_write(out_dir / "chronology.md", lines))

    # -- parties -----------------------------------------------------------
    first_seen: dict[str, EmailRecord] = {}
    last_seen: dict[str, EmailRecord] = {}
    counts: dict[str, int] = {}
    for r in records:
        for addr in _ADDR.findall(f"{r.sender} {r.recipients}"):
            a = addr.lower()
            first_seen.setdefault(a, r)
            last_seen[a] = r
            counts[a] = counts.get(a, 0) + 1
    lines = [
        f"# Parties — {case}",
        f"_Every address appearing in the corpus ({len(counts)} unique)_",
        "",
        "| Address | Messages | First seen | Last seen |",
        "|---|---|---|---|",
    ]
    for addr in sorted(counts, key=counts.get, reverse=True):
        f_, l_ = first_seen[addr], last_seen[addr]
        fd = f_.date.strftime("%Y-%m-%d") if f_.date else "—"
        ld = l_.date.strftime("%Y-%m-%d") if l_.date else "—"
        lines.append(f"| {addr} | {counts[addr]} | {fd} | {ld} |")
    written.append(_write(out_dir / "parties.md", lines))

    # -- exhibit index -----------------------------------------------------
    lines = [
        f"# Exhibit Index — {case}",
        "_Each attachment with its SHA-256 as extracted (chain of custody)._",
        "",
        "| # | Attachment | Type | SHA-256 | From email |",
        "|---|---|---|---|---|",
    ]
    n = 0
    for r in records:
        for name, ctype, sha in r.attachments:
            n += 1
            lines.append(
                f"| {n} | {name} | `{ctype}` | `{sha[:16]}…` "
                f"| [{r.subject}]({_rel(r.path, base)}) |"
            )
    written.append(_write(out_dir / "exhibit_index.md", lines))

    # -- privilege review queue --------------------------------------------
    flagged = [r for r in records if r.privileged_hits]
    lines = [
        f"# Privilege Review Queue — {case}",
        "_Keyword screen only. Review flagged items FIRST; absence of a flag_",
        "_is NOT a clearance. Nothing here is a privilege determination._",
        "",
        f"Flagged: **{len(flagged)}** of {len(records)} message(s).",
        "",
    ]
    for r in flagged:
        when = r.date.strftime("%Y-%m-%d") if r.date else "(undated)"
        lines.append(
            f"- [ ] **{r.subject}** ({when}, {r.sender}) — hits: "
            f"{', '.join(r.privileged_hits)} — [open]({_rel(r.path, base)})"
        )
    written.append(_write(out_dir / "privilege_review.md", lines))
    return written


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
