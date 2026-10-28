from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from foamstudio.app.crash import handle_exception


def test_crash_report_contains_the_traceback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FOAMSTUDIO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("FOAMSTUDIO_HEADLESS", "1")
    try:
        raise RuntimeError("boom-phase0")
    except RuntimeError:
        exc_type, exc, tb = sys.exc_info()
    handle_exception(exc_type, exc, tb, logging.getLogger("foamstudio"))
    text = (tmp_path / "logs" / "crash.log").read_text(encoding="utf-8")
    assert "boom-phase0" in text
    assert "RuntimeError" in text


def test_crash_report_write_failure_is_raised(
    monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("x", encoding="utf-8")
    monkeypatch.setenv("FOAMSTUDIO_STATE_DIR", str(blocked))
    monkeypatch.setenv("FOAMSTUDIO_HEADLESS", "1")
    caplog.set_level(logging.ERROR, logger="foamstudio")
    try:
        raise RuntimeError("still-reported")
    except RuntimeError:
        exc_type, exc, tb = sys.exc_info()
    with pytest.raises(OSError):
        handle_exception(exc_type, exc, tb, logging.getLogger("foamstudio"))
    assert "Could not write crash report" in caplog.text
