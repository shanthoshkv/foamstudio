"""Batch CLI must not need Qt: servers, HPC nodes, and CI runners often lack libEGL/X11."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BLOCK = """
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "PySide6" or name.startswith("PySide6."):
            raise ImportError("blocked " + name)
sys.meta_path.insert(0, Block())
from foamstudio.app.main import main
sys.exit(main(sys.argv[1:]))
"""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _BLOCK, *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[1],
        timeout=120,
    )


def test_batch_commands_run_without_pyside6(tmp_path: Path) -> None:
    project = tmp_path / "p"
    for args in (
        ("--version",),
        ("--write-case", "samples/cavity/case.json", "--project", str(project)),
        ("--block-mesh", "box", "--project", str(project)),
        ("--report", str(tmp_path / "r.html"), "--project", str(project)),
    ):
        done = _run(*args)
        assert done.returncode == 0, (args, done.stderr[-800:])
        assert "blocked" not in done.stderr
    assert (project / "case" / "system" / "controlDict").is_file()
    assert (tmp_path / "r.html").is_file()
