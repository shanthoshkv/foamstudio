"""Installer scripts exist and refuse to pretend they were signed or timed."""

from pathlib import Path

_ROOT = Path(__file__).parents[1]


def test_signing_script_refuses_without_a_certificate() -> None:
    text = (_ROOT / "packaging" / "signing" / "sign.ps1").read_text(encoding="utf-8")
    assert "FOAMSTUDIO_SIGN_PFX" in text
    assert "exit 2" in text


def test_fresh_vm_sheet_is_not_marked_done() -> None:
    text = (_ROOT / "packaging" / "FRESH_VM.md").read_text(encoding="utf-8")
    assert "not run" in text
    assert "**not** executed" in text


def test_appimage_helper_is_gated() -> None:
    text = (_ROOT / "packaging" / "linux" / "make-appimage.sh").read_text(encoding="utf-8")
    assert "FOAMSTUDIO_APPIMAGE" in text
    assert "exit 2" in text
