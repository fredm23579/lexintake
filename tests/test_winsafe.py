from pathlib import Path

from lexintake import winsafe


def test_sanitize_illegal_chars():
    assert winsafe.sanitize_component('RE: memo? <v2>|"x".docx') == "RE_ memo_ _v2___x_.docx"


def test_sanitize_reserved_device_names():
    assert winsafe.sanitize_component("CON.pdf").startswith("_")
    assert winsafe.sanitize_component("lpt1.txt") == "_lpt1.txt"  # case-insensitive
    assert winsafe.sanitize_component("CONTRACT.pdf") == "CONTRACT.pdf"  # not reserved


def test_sanitize_trailing_dots_and_spaces():
    assert winsafe.sanitize_component("exhibit. ") == "exhibit"
    assert winsafe.sanitize_component("   ") == "_unnamed"


def test_sanitize_truncates_stem_keeps_extension():
    out = winsafe.sanitize_component("x" * 300 + ".docx", max_len=50)
    assert len(out) <= 50
    assert out.endswith(".docx")


def test_extended_path_passthrough_short(tmp_path: Path):
    # Short paths come back unprefixed on every OS.
    assert "\\\\?\\" not in winsafe.extended_path(tmp_path / "a.txt")


def test_is_locked_false_for_normal_file(tmp_path: Path):
    f = tmp_path / "free.txt"
    f.write_text("x")
    assert winsafe.is_locked(f) is False


def test_is_cloud_synced():
    assert winsafe.is_cloud_synced(Path("/Users/x/OneDrive - Firm LLP/case"))
    assert not winsafe.is_cloud_synced(Path("/srv/local/case"))


def test_discover_mail_folders(tmp_path: Path):
    (tmp_path / "Documents" / "Outlook Files").mkdir(parents=True)
    (tmp_path / "Downloads").mkdir()
    found = dict(winsafe.discover_mail_folders(home=tmp_path))
    assert "Outlook saved mail" in found and "Downloads" in found
    assert "Clio exports" not in found


def test_safe_write_text_sanitizes_leaf(tmp_path: Path):
    out = winsafe.safe_write_text(tmp_path / 'bad:name?.md', "body")
    assert out.name == "bad_name_.md"
    assert out.read_text(encoding="utf-8") == "body"
