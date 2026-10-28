"""QWebChannel bridge to openfoam_case_generator.html.

Python calls ``applySpec`` and ``buildCaseFiles`` with ``runJavaScript``. The page calls
``py.onSpecChanged``. Dictionary text still comes only from the HTML generator.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QEventLoop, QFile, QIODevice, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget

from foamstudio.generator.headless import GeneratorFailure, repository_root

_REMOTE_SCRIPT = re.compile(
    r"<script\b[^>]*\bsrc\s*=\s*['\"][^'\"]+['\"][^>]*>\s*</script>",
    re.IGNORECASE,
)
_PAGE_COMMAND = "QWebEngine runJavaScript openfoam_case_generator.html"
_CHANNEL_FIX = (
    "Qt WebChannel did not connect to the generator page. "
    "qwebchannel.js must load from the PySide6 install, and the page must be shown "
    "with a display or xvfb. QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox --disable-gpu "
    "is set for the WebEngine process."
)
_LOAD_FIX = (
    "Qt WebEngine did not finish loading the case generator. "
    "On Linux use xvfb. Keep QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox --disable-gpu. "
    "Remote scripts in the HTML are removed before load, so this does not wait on a CDN."
)
_JS_FIX = (
    "The case generator rejected the spec. The message above is from validateSpec "
    "in openfoam_case_generator.html."
)

_APPLY_JS = """
(function () {
  try {
    if (typeof applySpec !== "function" || typeof buildCaseFiles !== "function") {
      return JSON.stringify({ok:false, error:"applySpec is not a function"});
    }
    var spec = JSON.parse(@@SPEC@@);
    applySpec(spec);
    var name = @@NAME@@;
    var files = buildCaseFiles(name);
    return JSON.stringify({
      ok:true, files:files, caseName:name,
      generator:spec.generator, openfoamVersion:spec.openfoamVersion
    });
  } catch (e) {
    return JSON.stringify({ok:false, error:String(e && e.stack || e)});
  }
})()
"""

_BUILD_CURRENT_JS = """
(function () {
  try {
    if (typeof buildCaseFiles !== "function" || typeof caseSpec !== "function") {
      return JSON.stringify({ok:false, error:"buildCaseFiles is not a function"});
    }
    var spec = caseSpec();
    var name = spec.caseName || "case";
    var files = buildCaseFiles(name);
    return JSON.stringify({
      ok:true, files:files, caseName:name,
      generator:spec.generator, openfoamVersion:spec.openfoamVersion
    });
  } catch (e) {
    return JSON.stringify({ok:false, error:String(e && e.stack || e)});
  }
})()
"""

_PATCH_JS = """
(function () {
  try {
    if (typeof applySpec !== "function" || typeof caseSpec !== "function") {
      return JSON.stringify({ok:false, error:"applySpec is not a function"});
    }
    var patches = @@PATCHES@@;
    var spec = caseSpec();
    spec.state.patches = patches;
    applySpec(spec);
    var applied = caseSpec().state.patches.map(function (p) { return {name:p.name, role:p.role}; });
    if (window.py && window.py.onSpecChanged) window.py.onSpecChanged(JSON.stringify(caseSpec()));
    return JSON.stringify({ok:true, patches:applied});
  } catch (e) {
    return JSON.stringify({ok:false, error:String(e && e.stack || e)});
  }
})()
"""

_HOOK_JS = """
(function () {
  if (window.__foamstudioHooked) return "hooked";
  window.__foamstudioHooked = true;
  function publish() {
    try {
      if (window.py && window.py.onSpecChanged && typeof caseSpec === "function") {
        window.py.onSpecChanged(JSON.stringify(caseSpec()));
      }
    } catch (e) {}
  }
  window.foamstudioPublishSpec = publish;
  if (typeof applySpec === "function") {
    var orig = applySpec;
    window.applySpec = function (spec) {
      var result = orig(spec);
      publish();
      return result;
    };
  }
  document.addEventListener("change", publish, true);
  publish();
  return "hooked";
})()
"""

_CHANNEL_JS = """
(function () {
  if (typeof QWebChannel !== "function") return "no-ctor";
  if (typeof qt === "undefined" || !qt.webChannelTransport) return "no-transport";
  new QWebChannel(qt.webChannelTransport, function (channel) {
    window.py = channel.objects.py;
    window.__pyReady = true;
  });
  return "started";
})()
"""


class GeneratorBridge(QObject):
    """Object registered as ``py`` in the page."""

    spec_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.last_spec: str | None = None

    @Slot(str)
    def onSpecChanged(self, payload: str) -> None:
        self.last_spec = payload
        self.spec_changed.emit(payload)


class _BlockRemote(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        if info.requestUrl().scheme() in ("http", "https"):
            info.block(True)


class _GeneratorPage(QWebEnginePage):
    """Qt 6 exposes javaScriptConsoleMessage as a method, not a signal."""

    def __init__(self, console: list[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._console = console

    def javaScriptConsoleMessage(
        self,
        _level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:
        self._console.append(f"{source_id}:{line_number}: {message}")
        del self._console[:-40]


class GeneratorSession(QObject):
    """One loaded generator page."""

    def __init__(self, parent: QObject | None = None, html_path: Path | None = None) -> None:
        super().__init__(parent)
        self.html_path = html_path or (repository_root() / "openfoam_case_generator.html")
        self.bridge = GeneratorBridge(self)
        self._console: list[str] = []
        self._loaded = False
        self._html: str | None = None
        self._generation = 0
        self._js_timer: QTimer | None = None
        widget_parent = parent if isinstance(parent, QWidget) else None
        self.view = QWebEngineView(widget_parent)
        self.view.setObjectName("generatorView")
        self._page = _GeneratorPage(self._console, self.view)
        self.view.setPage(self._page)
        self._blocker = _BlockRemote(self)
        self._page.profile().setUrlRequestInterceptor(self._blocker)
        self.channel = QWebChannel(self)
        self.channel.registerObject("py", self.bridge)
        self._page.setWebChannel(self.channel)

    def load(self, timeout_ms: int = 60000, *, fresh: bool = False) -> None:
        # applySpec assigns onto STATE and leaves keys from the previous spec.
        # A fresh load matches Node, which builds each case in a new page.
        if self._loaded and not fresh:
            return
        self._loaded = False
        if self._generation:
            self.view.setHtml("<html><head></head><body></body></html>")
            self._wait_until(
                "typeof buildCaseFiles === 'function' ? 'yes' : 'no'",
                "no",
                timeout_ms,
                "The previous generator page did not unload.",
                _LOAD_FIX,
            )
        if self._html is None:
            try:
                self._html = _strip_remote_scripts(self.html_path.read_text(encoding="utf-8"))
            except OSError as exc:
                raise self._fail(
                    f"QWebEngineView {self.html_path}",
                    str(exc),
                    "Set FOAMSTUDIO_REPO to the checkout that contains "
                    "openfoam_case_generator.html.",
                ) from exc
        self._generation += 1
        html = self._html.replace("<head>", f"<head><!--{self._generation}-->", 1)
        self.view.setHtml(html, QUrl.fromLocalFile(str(self.html_path)))
        self._wait_until(
            (
                "typeof buildCaseFiles === 'function' && "
                "typeof applySpec === 'function' ? 'yes' : 'no'"
            ),
            "yes",
            timeout_ms,
            "applySpec is not on window. The generator script did not load.",
            _LOAD_FIX,
        )
        self._exec(self._qwebchannel_source(), timeout_ms=30000)
        kind = self._exec("typeof QWebChannel === 'function' ? 'yes' : 'no'", timeout_ms=10000)
        if kind != "yes":
            raise self._fail(
                "QFile :/qtwebchannel/qwebchannel.js",
                f"typeof QWebChannel returned {kind!r}",
                _CHANNEL_FIX,
            )
        started = self._exec(_CHANNEL_JS, timeout_ms=10000)
        if started != "started":
            raise self._fail(
                _PAGE_COMMAND,
                f"QWebChannel init returned {started!r}",
                _CHANNEL_FIX,
            )
        self._wait_until(
            "window.__pyReady === true ? 'yes' : 'no'",
            "yes",
            10000,
            "QWebChannel did not publish the py object.",
            _CHANNEL_FIX,
        )
        hooked = self._exec(_HOOK_JS, timeout_ms=10000)
        if hooked != "hooked":
            raise self._fail(_PAGE_COMMAND, f"spec hook returned {hooked!r}", _CHANNEL_FIX)
        self._loaded = True

    def apply_and_build(
        self, spec_text: str, case_name: str, timeout_ms: int = 60000
    ) -> dict[str, str]:
        script = _APPLY_JS.replace("@@SPEC@@", json.dumps(spec_text)).replace(
            "@@NAME@@", json.dumps(case_name)
        )
        payload = self._payload(self._exec(script, timeout_ms=timeout_ms))
        return _files(payload)

    def build_current_async(
        self, callback: Callable[[dict[str, Any]], None], timeout_ms: int = 60000
    ) -> None:
        def done(result: object) -> None:
            try:
                callback(self._payload(result))
            except GeneratorFailure as exc:
                callback({"ok": False, "error": str(exc)})

        self._exec_async(_BUILD_CURRENT_JS, done, timeout_ms=timeout_ms)

    def set_patches(
        self,
        patches: list[dict[str, str]],
        timeout_ms: int = 30000,
    ) -> list[dict[str, str]]:
        script = _PATCH_JS.replace("@@PATCHES@@", json.dumps(patches))
        payload = self._payload(self._exec(script, timeout_ms=timeout_ms))
        applied = payload.get("patches")
        if not isinstance(applied, list):
            raise self._fail(_PAGE_COMMAND, "set_patches returned no patch list", _JS_FIX)
        rows: list[dict[str, str]] = []
        for item in cast(list[object], applied):
            if not isinstance(item, dict):
                raise self._fail(_PAGE_COMMAND, f"bad patch row {item!r}", _JS_FIX)
            row = cast(dict[str, Any], item)
            name = row.get("name")
            role = row.get("role")
            if not isinstance(name, str) or not isinstance(role, str):
                raise self._fail(_PAGE_COMMAND, f"bad patch row {item!r}", _JS_FIX)
            rows.append({"name": name, "role": role})
        return rows

    def _exec(self, script: str, *, timeout_ms: int) -> object:
        loop = QEventLoop()
        box: dict[str, object] = {}
        timer = QTimer(self)
        timer.setSingleShot(True)

        def finish(result: object) -> None:
            if "done" in box:
                return
            box["done"] = True
            box["result"] = result
            timer.stop()
            loop.quit()

        def timed_out() -> None:
            if "done" in box:
                return
            box["done"] = True
            box["timeout"] = True
            loop.quit()

        timer.timeout.connect(timed_out)
        timer.start(timeout_ms)
        self.view.page().runJavaScript(script, 0, finish)
        loop.exec()
        if box.get("timeout"):
            raise self._fail(
                _PAGE_COMMAND,
                "runJavaScript timed out",
                _LOAD_FIX,
                returncode=124,
            )
        return box.get("result")

    def _exec_async(
        self,
        script: str,
        callback: Callable[[object], None],
        *,
        timeout_ms: int,
    ) -> None:
        box: dict[str, bool] = {}

        def finish(result: object) -> None:
            if box.get("done"):
                return
            box["done"] = True
            if self._js_timer is not None:
                self._js_timer.stop()
            callback(result)

        def timed_out() -> None:
            finish({"ok": False, "error": "runJavaScript timed out", "timeout": True})

        self._js_timer = QTimer(self)
        self._js_timer.setSingleShot(True)
        self._js_timer.timeout.connect(timed_out)
        self._js_timer.start(timeout_ms)
        self.view.page().runJavaScript(script, 0, finish)

    def _wait_until(
        self,
        script: str,
        expected: str,
        timeout_ms: int,
        detail: str,
        suggestion: str,
    ) -> None:
        loop = QEventLoop()
        state: dict[str, bool] = {"done": False, "failed": False}

        def timed_out() -> None:
            if state["done"]:
                return
            state["done"] = True
            state["failed"] = True
            loop.quit()

        def on_result(result: object) -> None:
            if state["done"]:
                return
            if result == expected:
                state["done"] = True
                loop.quit()

        def poll() -> None:
            if not state["done"]:
                self.view.page().runJavaScript(script, 0, on_result)

        timer = QTimer(self)
        timer.setInterval(100)
        timer.timeout.connect(poll)
        killer = QTimer(self)
        killer.setSingleShot(True)
        killer.timeout.connect(timed_out)
        killer.start(timeout_ms)
        timer.start()
        poll()
        loop.exec()
        timer.stop()
        killer.stop()
        if state["failed"]:
            raise self._fail(_PAGE_COMMAND, detail, suggestion, returncode=124)

    def _payload(self, result: object) -> dict[str, Any]:
        if isinstance(result, dict) and result.get("timeout"):
            raise self._fail(_PAGE_COMMAND, "runJavaScript timed out", _LOAD_FIX, returncode=124)
        if not isinstance(result, str):
            raise self._fail(
                _PAGE_COMMAND,
                f"runJavaScript returned {result!r}",
                _LOAD_FIX,
            )
        try:
            data: object = json.loads(result)
        except json.JSONDecodeError as exc:
            raise self._fail(_PAGE_COMMAND, result[-2000:], _JS_FIX) from exc
        if not isinstance(data, dict):
            raise self._fail(_PAGE_COMMAND, result[-2000:], _JS_FIX)
        payload = cast(dict[str, Any], data)
        if not payload.get("ok"):
            raise self._fail(_PAGE_COMMAND, str(payload.get("error")), _JS_FIX)
        return payload

    def _qwebchannel_source(self) -> str:
        handle = QFile(":/qtwebchannel/qwebchannel.js")
        if not handle.open(QIODevice.OpenModeFlag.ReadOnly):
            detail = handle.errorString()
            raise self._fail("QFile :/qtwebchannel/qwebchannel.js", detail, _CHANNEL_FIX)
        try:
            return bytes(handle.readAll()).decode("utf-8")
        finally:
            handle.close()

    def _fail(
        self,
        command: str,
        detail: str,
        suggestion: str,
        *,
        returncode: int = 1,
    ) -> GeneratorFailure:
        console = "\n".join(self._console)
        tail = detail if not console else f"{detail}\n{console}"
        return GeneratorFailure(
            command=command,
            returncode=returncode,
            log_tail=tail or "(no output)",
            suggestion=suggestion,
        )


def _strip_remote_scripts(html: str) -> str:
    return _REMOTE_SCRIPT.sub("", html)


def _files(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload.get("files")
    if not isinstance(raw, dict) or not raw:
        raise GeneratorFailure(
            command=_PAGE_COMMAND,
            returncode=1,
            log_tail="buildCaseFiles returned no files",
            suggestion=_JS_FIX,
        )
    files: dict[str, str] = {}
    for key, value in cast(dict[str, Any], raw).items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise GeneratorFailure(
                command=_PAGE_COMMAND,
                returncode=1,
                log_tail=f"bad file entry {key!r}",
                suggestion=_JS_FIX,
            )
        files[key] = value
    return files
