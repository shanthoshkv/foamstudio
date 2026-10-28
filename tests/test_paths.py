from __future__ import annotations

from pathlib import Path

from foamstudio.core import paths


def test_state_dir_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FOAMSTUDIO_STATE_DIR", str(tmp_path))
    assert paths.state_dir() == tmp_path
    assert paths.log_dir() == tmp_path / "logs"
    assert paths.log_file_path() == tmp_path / "logs" / "foamstudio.log"
    assert paths.crash_report_path() == tmp_path / "logs" / "crash.log"


def test_windows_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FOAMSTUDIO_STATE_DIR", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.state_dir() == tmp_path / "FoamStudio"


def test_macos_default(monkeypatch) -> None:
    monkeypatch.delenv("FOAMSTUDIO_STATE_DIR", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(paths.Path, "home", staticmethod(lambda: Path("/Users/me")))
    assert paths.state_dir() == Path("/Users/me/Library/Application Support/FoamStudio")


def test_linux_xdg_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FOAMSTUDIO_STATE_DIR", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert paths.state_dir() == tmp_path / "foamstudio"


def test_linux_fallback_home(monkeypatch) -> None:
    monkeypatch.delenv("FOAMSTUDIO_STATE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths.Path, "home", staticmethod(lambda: Path("/home/me")))
    assert paths.state_dir() == Path("/home/me/.local/state/foamstudio")
