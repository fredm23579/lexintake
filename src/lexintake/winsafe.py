"""Windows hardening for legal file handling.

Law-firm machines have a specific failure profile this module neutralizes:

* **Long paths** — discovery filenames like
  ``RE FW RE Lucerne - Exhibit 14 (final) (final) (2).pdf`` inside nested
  OneDrive case folders routinely exceed the legacy 260-char ``MAX_PATH``.
* **Locked files** — Outlook, Word, Excel, and Acrobat keep exclusive handles
  on anything open; a pipeline that crashes on the first locked file is
  useless on a working attorney's machine.
* **Reserved / illegal names** — ``CON``, ``PRN``, ``NUL``..., plus
  ``<>:"/\\|?*`` and trailing dots/spaces, all legal in email subjects and
  all fatal as Windows filenames.
* **Sync + share roots** — OneDrive/SharePoint and UNC paths behave subtly
  differently (placeholder hydration, latency); we detect them so the CLI can
  warn rather than mysteriously stall.

Everything here is pure path/string logic plus one cheap open() probe, so it
is fully testable on any OS. Nothing imports pywin32.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Names Windows reserves regardless of extension (CON.pdf is still reserved).
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
# Characters NTFS forbids in a single path component.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Legacy MAX_PATH; the \\?\ prefix lifts it without requiring the registry opt-in.
MAX_PATH = 260


def is_windows() -> bool:
    """Check if the current operating system is Windows.
    
    This is used to selectively apply Windows-specific hardening logic
    (like extended path prefixes) only when necessary.
    """
    return sys.platform == "win32"


def sanitize_component(name: str, *, max_len: int = 120) -> str:
    """Make one filename component safe on NTFS without losing identity.

    Illegal characters become ``_``; reserved device names get a ``_``
    prefix; trailing dots/spaces (silently stripped by Win32, causing
    open-by-name mismatches) are removed; overlong components are truncated
    stem-first so the extension survives.
    """
    cleaned = _ILLEGAL.sub("_", name).rstrip(". ")
    if not cleaned:
        cleaned = "_unnamed"
    stem, dot, ext = cleaned.partition(".")
    if stem.upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    if len(cleaned) > max_len:
        # Keep the extension; truncate the stem. Hash-suffixed names produced
        # upstream keep their uniqueness because the hash sits at the stem end.
        keep = max_len - len(ext) - (1 if dot else 0)
        cleaned = stem[:keep] + (dot + ext if dot else "")
    return cleaned


def extended_path(path: Path) -> str:
    r"""Return a string form safe past MAX_PATH on Windows (``\\?\`` form).

    On non-Windows platforms the plain path is returned unchanged, so callers
    can use this unconditionally. This prevents PathTooLong exceptions when
    dealing with deeply nested directories or extremely long file names common
    in discovery and legal documents.
    """
    # Resolve the path to an absolute path
    p = Path(path).resolve()
    s = str(p)
    # If not on Windows, or already prefixed, or short enough, do nothing
    if not is_windows() or s.startswith("\\\\?\\") or len(s) < MAX_PATH - 12:
        return s
    
    # Handle UNC paths (e.g. \\server\share) specially
    if s.startswith("\\\\"):                  # UNC share -> \\?\UNC\server\...
        return "\\\\?\\UNC" + s[1:]
    
    # Normal local path
    return "\\\\?\\" + s


def is_locked(path: Path) -> bool:
    """Best-effort probe for an exclusive lock held by another process.

    On Windows, opening for append fails with ``PermissionError`` while Word/
    Outlook/Acrobat hold the handle. On POSIX the probe almost always
    succeeds, which is correct: there is nothing to dodge there.
    """
    try:
        with open(path, "ab"):
            return False
    except (PermissionError, OSError):
        return True


def is_cloud_synced(path: Path) -> bool:
    """True when *path* lives under OneDrive/SharePoint sync or a UNC share.
    
    This is useful for detecting environments where file operations might be
    slowed down or altered by network latency and cloud sync mechanisms.
    """
    # Convert path to absolute, lowercased string for inspection
    s = str(Path(path).resolve()).lower()
    
    # UNC paths are generally network drives or cloud-mounted shares
    if s.startswith("\\\\"):
        return True
        
    # Check for common sync service names in the path components
    markers = ("onedrive", "sharepoint")
    return any(m in part for part in s.replace("/", "\\").split("\\") for m in markers)


# Well-known export drop folders for the products attorneys actually use.
# Each entry: (label, candidate path relative to the user profile).
_KNOWN_EXPORT_DIRS: tuple[tuple[str, str], ...] = (
    ("Outlook saved mail", "Documents/Outlook Files"),
    ("Downloads", "Downloads"),
    ("Clio exports", "Documents/Clio"),
    ("iManage checkouts", "iManage Work"),
    ("NetDocuments echo", "ND Office Echo"),
)


def discover_mail_folders(home: Path | None = None) -> list[tuple[str, Path]]:
    """Existing well-known mail/export folders on this machine, for `doctor`."""
    base = Path(home) if home else Path(os.environ.get("USERPROFILE", Path.home()))
    found = []
    for label, rel in _KNOWN_EXPORT_DIRS:
        candidate = base / rel
        if candidate.is_dir():
            found.append((label, candidate))
    return found


def safe_write_text(path: Path, text: str) -> Path:
    """Write text honoring long paths and sanitized leaf names.

    The parent chain is created as-is (callers control it); only the leaf is
    sanitized, so deterministic content-hash names survive intact.
    """
    target = path.with_name(sanitize_component(path.name))
    target.parent.mkdir(parents=True, exist_ok=True)
    Path(extended_path(target)).write_text(text, encoding="utf-8")
    return target
