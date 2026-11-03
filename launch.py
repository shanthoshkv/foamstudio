"""Launcher: first run builds the venv (progress in this console), then starts FoamStudio in it.

Needs only a stock Python 3.11+. Usage: python launch.py [FoamStudio args]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from foamstudio.core import setup_env  # noqa: E402  (stdlib-only module)

py = setup_env.venv_python()
if not py.is_file() or any(v is None for _, v in setup_env.check_libs(py)):
    print(f"First run: building {setup_env.venv_dir()} ...", flush=True)
    if not setup_env.install_venv(lambda line: print(line, flush=True), missing_only=True):
        sys.exit("Library install failed; see the output above.")
raise SystemExit(setup_env.relaunch_in_venv(sys.argv[1:]) or 0)
