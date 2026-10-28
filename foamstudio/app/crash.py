"""Write uncaught exceptions to disk and, when a window exists, show them."""

from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path
from types import TracebackType

from PySide6.QtWidgets import QApplication, QMessageBox

from foamstudio.core.paths import crash_report_path
from foamstudio.core.telemetry import TelemetryError, maybe_upload, post_report


def handle_exception(
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: TracebackType | None,
    logger: logging.Logger,
) -> None:
    if exc_type is None or exc is None:
        raise RuntimeError("handle_exception was called without an exception.")
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    logger.critical("Uncaught exception\n%s", text)
    path = crash_report_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as err:
        logger.error("Could not write crash report to %s: %s", path, err)
        raise
    _upload_crash(path, logger)
    app = QApplication.instance()
    if isinstance(app, QApplication) and os.environ.get("FOAMSTUDIO_HEADLESS") != "1":
        tail = "\n".join(text.splitlines()[-20:])
        QMessageBox.critical(
            None,
            "FoamStudio",
            f"Unexpected error: {exc}\n\nDetails written to:\n{path}\n\n{tail}",
        )


def _reports_enabled() -> bool:
    if os.environ.get("FOAMSTUDIO_CRASH_REPORTS") == "1":
        return True
    try:
        from foamstudio.app.settings import AppSettings

        return AppSettings().load().crash_reports
    except Exception:
        return False


def _upload_crash(path: Path, logger: logging.Logger) -> None:
    endpoint = os.environ.get("FOAMSTUDIO_CRASH_URL")
    try:
        plan = maybe_upload(path, enabled=_reports_enabled(), endpoint=endpoint)
    except TelemetryError as exc:
        logger.error("%s", exc)
        return
    if plan is None or os.environ.get("FOAMSTUDIO_CRASH_UPLOAD") != "1":
        return
    try:
        status = post_report(plan)
    except Exception as exc:
        logger.error("Crash upload failed: %s\n\nThe local report is still at %s", exc, path)
        return
    logger.info("Crash report uploaded (%s) to %s", status, plan.endpoint)


def install_crash_handler(logger: logging.Logger) -> None:
    def _hook(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        handle_exception(exc_type, exc, tb, logger)

    sys.excepthook = _hook
