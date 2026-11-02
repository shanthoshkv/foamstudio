"""Background run across a real FoamStudio restart.

    python scripts/detach_e2e.py RUNTIME_JSON

Phase 1 (own process): create the cavity demo with a long endTime, start it with
"Keep running if FoamStudio closes", then quit the app completely.
Phase 2 (new process): the solver must still be running; opening the project must
reattach (log view updating), and Stop must kill it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve()


def solver_count(rt: dict[str, str]) -> int:
    argv = (
        ["wsl.exe", "-d", rt["distro"], "--", "pgrep", "-c", "-f", "Foam"]
        if rt["kind"] == "wsl"
        else ["pgrep", "-c", "-f", "Foam"]
    )
    out = subprocess.run(argv, capture_output=True, text=True).stdout.strip()
    return int(out or 0)


def iterations(case: Path) -> int:
    logs = list(case.glob("log.*Foam"))
    return len(re.findall(r"^Time = ", logs[0].read_text(errors="replace"), re.M)) if logs else 0


def window(work: Path, rt: dict[str, str]):  # type: ignore[no-untyped-def]
    os.environ["FOAMSTUDIO_STATE_DIR"] = str(work / "state")
    os.environ["USERPROFILE"] = os.environ["HOME"] = str(work)
    from foamstudio.app.main import build_application
    from foamstudio.core.runtime.model import Installation

    app, win, inst = build_application([])
    win._store.save_runtime(Installation.from_dict(rt))
    win.show()
    return app, win, inst


def wait(app, cond, timeout: float) -> bool:  # type: ignore[no-untyped-def]
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.3)
    return False


def phase_start(work: Path, rt: dict[str, str]) -> None:
    app, win, inst = window(work, rt)
    from foamstudio.core.workspace import templates

    project = win.create_from_spec(work / "bg", templates()["cavity/case"])
    control = project.case_dir / "system" / "controlDict"
    text = re.sub(r"^endTime\s+[^;]+;", "endTime 100000;", control.read_text(), flags=re.M)
    control.write_text(
        re.sub(r"^writeInterval\s+[^;]+;", "writeInterval 100000;", text, flags=re.M)
    )
    win._show_run_panel()
    win._run_panel.processes.setValue(1)
    win._run_panel.detached.setChecked(True)
    win.start_solver()
    ok = wait(app, lambda: iterations(project.case_dir) > 20, 180)
    print(f"phase1 started={ok} iterations={iterations(project.case_dir)}", flush=True)
    win.close()
    inst.close()
    app.quit()


def phase_resume(work: Path, rt: dict[str, str]) -> None:
    app, win, inst = window(work, rt)
    project = win.open_project_path(work / "bg")
    case = project.case_dir
    before = iterations(case)
    wait(app, lambda: False, 1)
    status = win.statusBar().currentMessage()
    grew = wait(app, lambda: iterations(case) > before + 5, 60)
    wait(app, lambda: win._residual_plot is not None, 30)  # the log view refreshes every 2 s
    plot_text = win._residual_plot.summary.text() if win._residual_plot else ""
    print(f"phase2 status={status!r} grew={grew} plot={bool(plot_text)}", flush=True)
    wait(app, lambda: (case / ".foamstudio" / "job.pid").is_file(), 30)
    win.stop_solver()
    gone = wait(app, lambda: solver_count(rt) == 0, 60)
    print(f"phase2 stopped={gone}", flush=True)
    win.close()
    inst.close()
    app.quit()


def main() -> int:
    if len(sys.argv) == 4:
        work, rt = Path(sys.argv[2]), json.loads(Path(sys.argv[3]).read_text())
        (phase_start if sys.argv[1] == "start" else phase_resume)(work, rt)
        return 0
    runtime = sys.argv[1]
    rt = json.loads(Path(runtime).read_text())
    work = Path(tempfile.mkdtemp(prefix="fs-detach-"))
    py = sys.executable
    one = subprocess.run(
        [py, "-u", str(HERE), "start", str(work), runtime],
        capture_output=True,
        text=True,
        timeout=600,
    )
    print(one.stdout.strip().splitlines()[-1] if one.stdout.strip() else one.stderr[-800:])
    alive = solver_count(rt)
    print(f"after app exit: solver processes = {alive}")
    two = subprocess.run(
        [py, "-u", str(HERE), "resume", str(work), runtime],
        capture_output=True,
        text=True,
        timeout=600,
    )
    lines = [line for line in two.stdout.splitlines() if line.startswith("phase2")]
    print("\n".join(lines) or two.stderr[-800:])
    passed = (
        "started=True" in one.stdout
        and alive > 0
        and any(all(k in line for k in ("Reattached", "grew=True", "plot=True")) for line in lines)
        and any("stopped=True" in line for line in lines)
    )
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
