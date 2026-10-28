"""Qt WebEngine byte-identity check. Run with a display or xvfb, not offscreen.

Usage: python tests/bridge_check.py
Prints BRIDGE OK on success. Differences and WebEngine errors go to stderr.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    from foamstudio.generator.bridge import GeneratorSession
    from foamstudio.generator.headless import GeneratorFailure, first_difference, relativize
    from foamstudio.generator.solvers import SOLVERS, TAGGED_CASES, golden_key

    golden_path = Path(__file__).resolve().parent / "golden" / "v2412.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    keys = [golden_key(solver) for solver in SOLVERS]
    keys.extend(TAGGED_CASES)
    if len(SOLVERS) != 25:
        return _fail(f"expected 25 solvers, found {len(SOLVERS)}")
    session = GeneratorSession()
    for key in keys:
        case = golden[key]
        spec_text = case["case.json"]
        spec = json.loads(spec_text)
        name = str(spec["caseName"])
        try:
            session.load(fresh=True)
            files = session.apply_and_build(spec_text, name)
        except GeneratorFailure as exc:
            return _fail(f"{key}\n{exc}")
        got = relativize(files, name)
        expected = case
        for path in sorted(set(got) | set(expected)):
            if path not in expected:
                return _fail(f"{key}/{path}: added")
            if path not in got:
                return _fail(f"{key}/{path}: removed")
            if got[path] != expected[path]:
                return _fail(f"{key}/{path}: {first_difference(expected[path], got[path])}")
        print(key, file=sys.stderr, flush=True)
    try:
        applied = session.set_patches(
            [
                {"name": "inlet", "role": "inlet"},
                {"name": "walls", "role": "wall"},
            ]
        )
    except GeneratorFailure as exc:
        return _fail(str(exc))
    roles = {row["name"]: row["role"] for row in applied}
    if roles.get("inlet") != "inlet" or roles.get("walls") != "wall":
        return _fail(f"set_patches returned {applied!r}")
    deadline = time.monotonic() + 5
    while session.bridge.last_spec is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.05)
    if session.bridge.last_spec is None:
        return _fail(
            "QWebChannel did not deliver py.onSpecChanged.\n" + "\n".join(session._console)
        )
    if "inlet" not in session.bridge.last_spec or "walls" not in session.bridge.last_spec:
        return _fail(
            f"onSpecChanged payload did not include the pushed patches: {session.bridge.last_spec}"
        )
    print("BRIDGE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"WebEngine bridge failed to start: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
