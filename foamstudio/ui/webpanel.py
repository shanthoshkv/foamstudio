"""Hybrid UI: HTML/CSS/JS pages in Qt WebEngine, talking to Python over QWebChannel.

No port is opened: the page is a local file and the channel is in-process. File dialogs,
the 3D viewer, WSL and processes stay native; the page only asks the host to act.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QFile, QIODevice, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

WEB = Path(__file__).resolve().parent / "web"


class Bridge(QObject):
    """Exposed to the page as `py`: state() pulls, updated pushes, action() calls the host."""

    updated = Signal(str)

    def __init__(self, host: Any) -> None:
        super().__init__(host)
        self.host = host

    @Slot(result=str)
    def state(self) -> str:
        return json.dumps(self.host.dashboard_state())

    @Slot(str, str)
    def action(self, name: str, arg: str) -> None:
        self.host.dashboard_action(name, arg)
        self.push()

    def push(self) -> None:
        self.updated.emit(self.state())


def _channel_script() -> str:
    handle = QFile(":/qtwebchannel/qwebchannel.js")
    if not handle.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError("qwebchannel.js is missing from the PySide6 install.")
    return bytes(handle.readAll().data()).decode("utf-8")


class WebPage(QWidget):
    """A page from foamstudio/ui/web with the bridge attached and refreshed every 2 s."""

    def __init__(self, host: Any, page: str = "dashboard.html") -> None:
        super().__init__(host)
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
        from PySide6.QtWebEngineWidgets import QWebEngineView

        class _Page(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):  # type: ignore[no-untyped-def]
                logging.getLogger("foamstudio").info(
                    "web %s:%s: %s", Path(source).name, line, message
                )

        self.setObjectName("webPage")
        self.view = QWebEngineView(self)
        self.view.setPage(_Page(self.view))
        self.bridge = Bridge(host)
        self.channel = QWebChannel(self)
        self.channel.registerObject("py", self.bridge)
        self.view.page().setWebChannel(self.channel)
        script = QWebEngineScript()
        script.setSourceCode(_channel_script())
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self.view.page().scripts().insert(script)
        self.view.setUrl(QUrl.fromLocalFile(str(WEB / page)))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.bridge.push)
        self.timer.start(2000)


def series(xs: list[float], ys: list[float], limit: int = 600) -> list[list[float]]:
    """[[x, y], ...] thinned to about `limit` points so the page stays fast."""
    step = max(1, len(xs) // limit)
    points = [[x, y] for x, y in zip(xs[::step], ys[::step], strict=False)]
    if xs and points[-1][0] != xs[-1]:
        points.append([xs[-1], ys[-1]])
    return points
