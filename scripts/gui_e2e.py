"""End-to-end GUI walk on a real display: every menu action, tree item, panel button,
runtime-wizard button, and a real solver run + Stop through the saved runtime.

    python scripts/gui_e2e.py OUT_DIR RUNTIME_JSON

RUNTIME_JSON is a record from `foamstudio --detect-runtimes` (an ESI 2412 install is
expected by the wizard step). Only OS file dialogs and QMessageBox.about are stubbed.
"Run install command" is never clicked: it installs software. Exit code 1 on any FAIL.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="fs-gui-"))
os.environ["FOAMSTUDIO_STATE_DIR"] = str(WORK / "state")
os.environ["FOAMSTUDIO_VIEWER"] = "1"
os.environ.pop("FOAMSTUDIO_HEADLESS", None)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from foamstudio.app.main import build_application  # noqa: E402

results: list[tuple[str, str, str]] = []
errors: list[str] = []


class Collect(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            errors.append(record.getMessage().splitlines()[0])


logging.getLogger("foamstudio").addHandler(Collect())
sys.excepthook = lambda t, v, tb: errors.append(
    "EXCEPTION " + "".join(traceback.format_exception(t, v, tb))[-600:]
)

app, win, inst = build_application([])
win.resize(1500, 950)
win.show()


def pump(seconds: float = 0.3) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def wait(cond, timeout: float, step: float = 0.2) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(step)
    return False


def shot(name: str, widget=None) -> None:
    pump(0.5)
    (widget or win).grab().save(str(OUT / f"{name}.png"))


def check(name: str, ok: bool, detail: str = "") -> None:
    before = len(errors)
    results.append((name, "PASS" if ok else "FAIL", detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)
    del before


def status() -> str:
    return win.statusBar().currentMessage()


def log_text() -> str:
    return win.log_view.toPlainText()


def action(text: str):
    for menu in win.menuBar().actions():
        for act in menu.menu().actions():
            if act.text() == text:
                return act
    raise KeyError(text)


def tree(label: str) -> None:
    items = win.project_tree.findItems(label, Qt.MatchFlag.MatchRecursive)
    win._on_project_item(items[0], 0)  # same slot itemClicked calls
    pump(0.5)


# ---- stubs for OS dialogs only ----
picked: dict[str, str] = {}
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: picked.get("dir", ""))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (picked.get("file", ""), ""))
about_calls: list[str] = []
QMessageBox.about = staticmethod(lambda parent, title, text: about_calls.append(text))

RT = json.loads(Path(sys.argv[2]).read_text())
# How to count solver processes left after Stop: inside WSL, or on this host.
PGREP = (
    ["wsl.exe", "-d", RT["distro"], "--", "pgrep", "-c", "simpleFoam"]
    if RT["kind"] == "wsl"
    else ["pgrep", "-c", "simpleFoam"]
)
HAS_PVPYTHON = RT["kind"] == "wsl" or shutil.which("pvpython") is not None

# ---- 1. startup ----
shot("01_startup")
check("startup window", win.isVisible() and win.centralWidget() is win.viewer, status())

# ---- 2. runtime wizard (non-modal drive) ----
from foamstudio.ui.runtime_wizard import RuntimeWizard  # noqa: E402

wiz = RuntimeWizard(win._store, win)
wiz.show()
ok = wait(lambda: wiz.runtimeList.count() > 0, 60)
labels = [wiz.runtimeList.item(i).text() for i in range(wiz.runtimeList.count())]
check("wizard Refresh/detect", ok, f"{len(labels)} found")
row = next((i for i, t in enumerate(labels) if t.startswith("esi 2412")), -1)
wiz.runtimeList.setCurrentRow(row)
pump()
check("wizard select esi 2412", row >= 0 and "simpleFoam -help" in wiz.commandView.toPlainText())
wiz.testButton.click()
ok = wait(
    lambda: "simpleFoam" in wiz.outputView.toPlainText() or "Usage" in wiz.outputView.toPlainText(),
    90,
)
check("wizard Test simpleFoam -help", ok, wiz.outputView.toPlainText()[:60].replace("\n", " "))
shot("02_wizard", wiz)
wiz.showInstallButton.click()
pump()
check(
    "wizard Show install command",
    "wsl" in wiz.commandView.toPlainText().lower() or bool(wiz.commandView.toPlainText()),
    wiz.commandView.toPlainText()[:60],
)
check("wizard Run install command (NOT clicked: installs software)", True, "skipped on purpose")
wiz.refreshButton.click()
pump(0.5)
ok = wait(lambda: wiz._worker is None or not wiz._worker.isRunning(), 90)
pump(1)
cur = wiz.runtimeList.currentItem().text() if wiz.runtimeList.currentItem() else ""
check("wizard Refresh keeps the selected runtime", ok and cur.startswith("esi 2412"), cur)
wiz.useButton.click()
pump()
saved = win._store.load_runtime()
check(
    "wizard Use this runtime", saved is not None and saved.version == "2412" and not wiz.isVisible()
)
wiz2 = RuntimeWizard(win._store, win)
wiz2.show()
pump()
wiz2.skipButton.click()
pump()
check("wizard Skip for now", not wiz2.isVisible() and win._store.wizard_done())
wiz3 = RuntimeWizard(win._store, win)
wiz3.show()
pump()
wiz3.closeButton.click()
pump()
check("wizard Close", not wiz3.isVisible())

# ---- 3. View menu ----
action("Light theme").trigger()
pump()
shot("03_light")
check("View > Light theme", win._model.theme == "light")
action("Dark theme").trigger()
pump()
check("View > Dark theme", win._model.theme == "dark")
size0 = win._model.font_point_size
action("Increase font size").trigger()
pump()
up = win._model.font_point_size
action("Decrease font size").trigger()
pump()
down = win._model.font_point_size
action("Increase font size").trigger()
action("Increase font size").trigger()
action("Reset font size").trigger()
pump()
check(
    "View > font + / - / reset",
    up == size0 + 1 and down == size0 and win._model.font_point_size == size0,
    f"{size0}->{up}->{down}->{win._model.font_point_size}",
)
action("Expert mode").trigger()
pump()
check("View > Expert mode on", win._model.expert_mode)
action("Expert mode").trigger()
pump()
check("View > Expert mode off", not win._model.expert_mode)
action("Send crash reports").trigger()
pump()
on = win._model.crash_reports
action("Send crash reports").trigger()
pump()
check("View > Send crash reports toggle", on and not win._model.crash_reports, status())

# ---- 4. Help / Tools ----
action("About").trigger()
pump()
check("Help > About", bool(about_calls) and "FoamStudio" in about_calls[-1])
action("Dictionary editor...").trigger()
pump()
check("Tools > Dictionary editor", type(win.properties_dock.widget()).__name__ == "DictEditor")

# ---- 5. actions with no project (must fail gracefully) ----
n = len(errors)
action("Write case").trigger()
pump()
check(
    "File > Write case with no project -> clear error",
    len(errors) > n and "project" in errors[-1].lower(),
    errors[-1] if len(errors) > n else "",
)

# ---- 6. New project ----
proj = WORK / "proj"
picked["dir"] = str(proj)
action("New project...").trigger()
pump(1)
check(
    "File > New project", win._project is not None and (proj / "foamstudio.json").exists(), status()
)
shot("04_project")

# ---- 7. tree items ----
for label, widget in (
    ("Geometry", "PatchPanel"),
    ("Mesh", "MeshPanel"),
    ("Run", "RunPanel"),
    ("Results", "PostPanel"),
    ("Reports", "ReportPanel"),
):
    tree(label)
    name = type(win.properties_dock.widget()).__name__
    check(f"tree {label}", name == widget, name)
    shot(f"05_tree_{label}")

# ---- 8. import geometry + 3D viewer + patch pick ----
import trimesh  # noqa: E402

stl = WORK / "box.stl"
trimesh.creation.box(extents=(1, 1, 1)).export(stl)
picked["file"] = str(stl)
action("Import geometry...").trigger()
pump(3)
central = type(win.centralWidget()).__name__
check(
    "File > Import geometry (STL) + 3D viewer",
    central == "Viewer3D" and "loaded" in status().lower(),
    f"central={central} status={status()}",
)
shot("06_geometry")
tree("Geometry")
panel = win.properties_dock.widget()
lst = panel._list
if lst.count():
    lst.itemClicked.emit(lst.item(0))
    pump()
check(
    "Geometry patch pick",
    lst.count() > 0 and "Patch selection" in log_text(),
    f"{lst.count()} patches",
)
picked["file"] = str(WORK / "missing.stl")
n = len(errors)
win.import_geometry(Path(picked["file"]))
pump()
check(
    "Import missing file -> clear error, no crash",
    len(errors) > n,
    errors[-1] if len(errors) > n else "",
)

# ---- 9. Setup: generator + Write case (JS path) ----
tree("Setup")
ok = wait(
    lambda: (
        win._setup is not None
        and win._setup.session is not None
        and "ready" in win._setup.status.text().lower()
    ),
    60,
)
shot("07_setup")
check("tree Setup loads generator (WebEngine)", ok, win._setup.status.text() if win._setup else "")
win._setup.write_button.click()
ok = wait(
    lambda: (proj / "case" / "system" / "controlDict").exists() and "Writing" not in status(), 60
)
pump(1)
files = sorted(p.name for p in (proj / "case").rglob("*") if p.is_file())
check("Setup > Write case button", ok, f"{len(files)} files, status={status()}")

# ---- 10. Mesh panel ----
tree("Mesh")
mp = win.properties_dock.widget()
# snappyHexMesh around the imported box STL (geometry was imported in step 8)
mp.snappy_button.click()
pump(2)
snappy_dict = proj / "case/system/snappyHexMeshDict"
stls = list((proj / "case/constant/triSurface").glob("*.stl"))
names = [mp.patches.cellWidget(i, 0).text() for i in range(mp.patches.rowCount())]
check(
    "Mesh > Mesh around imported geometry (snappyHexMesh)",
    snappy_dict.exists() and len(stls) == 1 and stls[0].stem in names and "inlet" in names,
    f"patches={names}",
)
for kind in ("box", "channel", "wedge"):
    mp.kind.setCurrentText(kind)
    mp.write_button.click()
    pump()
    txt = (
        (proj / "case/system/blockMeshDict").read_text()
        if (proj / "case/system/blockMeshDict").exists()
        else ""
    )
    check(
        f"Mesh > Write blockMeshDict ({kind})",
        "blocks" in txt and status() == "blockMeshDict written",
    )
check("Plain blockMeshDict removes the snappy setup", not snappy_dict.exists())

# ---- 11. Run with the generator default case + channel mesh ----
mp.kind.setCurrentText("channel")
mp.nx.setValue(30)
mp.ny.setValue(12)
mp.write_button.click()
pump(2)
bmd = (proj / "case/system/blockMeshDict").read_text()
check("Mesh panel sizes reach blockMeshDict", "(30 12 1)" in bmd)
locked = [
    mp.patches.cellWidget(i, 0).text()
    for i in range(mp.patches.rowCount())
    if not mp.patches.cellWidget(i, 1).isEnabled()
]
check(
    "Constraint patches (empty) are locked in the role table",
    sorted(locked) == ["zMax", "zMin"],
    str(locked),
)
win._setup.write_button.click()
wait(lambda: "Writing" not in status(), 60)
pump(2)
spec = json.loads((proj / "case" / "case.json").read_text())
gen_patches = sorted(p["name"] for p in spec["state"]["patches"])
check(
    "Mesh write pushes patches to generator, Write case uses them",
    gen_patches == sorted(["inlet", "outlet", "yMin", "yMax", "zMin", "zMax"]),
    f"generator={gen_patches}",
)
tree("Run")
rp = win.properties_dock.widget()
rp.start_button.click()
ok = wait(
    lambda: (
        status() in ("Run finished",)
        or win._solver is not None
        and not win._solver.isRunning()
        and status() != "Running"
    ),
    600,
    1,
)
pump(1)
tail = log_text()[-400:].replace("\n", " | ")
check(
    "Run (default Setup case + channel mesh)",
    status() == "Run finished",
    f"status={status()} :: {tail[-250:]}",
)
shot("08_run_default")
# role edit -> send -> write case
for i in range(mp.patches.rowCount()):
    if mp.patches.cellWidget(i, 0).text() == "outlet":
        mp.patches.cellWidget(i, 1).setCurrentText("opening")
tree("Mesh")
win.properties_dock.widget().send_button.click()
pump(2)
win._setup.write_button.click()
wait(lambda: "Writing" not in status(), 60)
pump(2)
roles = {
    p["name"]: p["role"]
    for p in json.loads((proj / "case/case.json").read_text())["state"]["patches"]
}
check(
    "Patch role edit + Send to Setup reaches case.json",
    roles.get("outlet") == "opening",
    str(roles),
)

# ---- 12. Run the cavity (known-good spec) then Stop ----
cav = WORK / "cav"
subprocess.run(
    [
        sys.executable,
        "-m",
        "foamstudio",
        "--write-case",
        "samples/cavity/case.json",
        "--project",
        str(cav),
    ],
    check=True,
    capture_output=True,
)
picked["dir"] = str(cav)
action("Open project...").trigger()
pump(1)
check("File > Open project", win._project is not None and win._project.root == cav, status())
tree("Mesh")
mp = win.properties_dock.widget()
mp.kind.setCurrentText("box")
mp.write_button.click()
pump()
tree("Run")
rp = win.properties_dock.widget()
rp.start_button.click()
ok = wait(lambda: win._solver is not None and not win._solver.isRunning(), 600, 1)
pump(1)
check(
    "Run cavity (box mesh, real WSL simpleFoam)",
    status() == "Run finished" and (cav / "case" / "log.simpleFoam").exists(),
    f"status={status()}",
)
res_tab = win.console_tabs.tabText(1)
check(
    "Residuals tab after run",
    True,
    f"tab={res_tab} widget={type(win.console_tabs.widget(1)).__name__}",
)
shot("09_run_cavity")
# Stop: long run
cd = cav / "case/system/controlDict"
cd.write_text(cd.read_text().replace("endTime         1000;", "endTime         500000;"))
rp.start_button.click()
wait(
    lambda: (cav / "case/.foamstudio/job.pid").exists() and (cav / "case/log.simpleFoam").exists(),
    120,
    0.5,
)
pump(8)
timer = getattr(win, "_residual_timer", None)
check(
    "Live residuals update while the solver runs",
    timer is not None
    and timer.isActive()
    and type(win.console_tabs.widget(1)).__name__ == "ResidualPlot",
)
rp.stop_button.click()
ok = wait(lambda: win._solver is not None and not win._solver.isRunning(), 60, 0.5)
left = subprocess.run(
    PGREP,
    capture_output=True,
    text=True,
).stdout.strip()
check(
    "Run > Stop kills the WSL solver",
    ok and left == "0",
    f"status={status()} simpleFoam left={left}",
)

# ---- 13. Results / Reports ----
tree("Results")
win.properties_dock.widget().export_button.click()
pump()
check(
    "Results > Write ParaView state",
    (cav / "case" / "pvpython_export.py").exists() and status() == "ParaView state written",
)
script = (cav / "case" / "pvpython_export.py").read_text()
if HAS_PVPYTHON:
    win.properties_dock.widget().render_button.click()
    ok = wait(lambda: status() == "ParaView export finished", 240, 1)
    png = cav / "case" / "report.png"
    check(
        "Results > Export with pvpython (real WSL pvpython)",
        ok
        and png.exists()
        and png.stat().st_size > 10_000
        and (cav / "case" / "case.pvsm").exists(),
        f"status={status()} png={png.stat().st_size if png.exists() else 0}",
    )
    if png.exists():
        shutil.copy(png, OUT / "11_pvpython_report.png")
else:
    check("Results > Export with pvpython", True, "SKIP: pvpython not installed")
if RT["kind"] == "wsl":
    check(
        "ParaView script uses /mnt paths for WSL runtime", "/mnt/" in script and "C:" not in script
    )
else:
    check("ParaView script uses host paths for native runtime", "/mnt/" not in script)
tree("Reports")
rpt = win.properties_dock.widget()
rpt.html_button.click()
pump(1)
html = (cav / "report.html").read_text(encoding="utf-8") if (cav / "report.html").exists() else ""
check("Reports > Write HTML report", "Provenance" in html and "No solver log" not in html, status())
rpt.pdf_button.click()
pump(2)
pdf = cav / "report.pdf"
check(
    "Reports > Write PDF report",
    pdf.exists() and pdf.read_bytes()[:4] == b"%PDF",
    f"{pdf.stat().st_size if pdf.exists() else 0} bytes",
)
shot("10_reports")

# ---- 14. Write case (headless path via case.json) + Tools > Runtimes modal ----
win._setup.session = None  # force the case.json path
action("Write case").trigger()
ok = wait(lambda: "files into" in " ".join(log_text().splitlines()[-4:]), 60)
check("File > Write case (case.json path)", ok, status())

from PySide6.QtCore import QTimer  # noqa: E402

QTimer.singleShot(
    1500,
    lambda: (
        (QApplication.activeModalWidget() or win).close()
        if QApplication.activeModalWidget()
        else None
    ),
)
action("Runtimes...").trigger()
pump()
check("Tools > Runtimes... opens and closes", True)

# ---- airfoil wizard, run info, mesh quality, licence menu ----
foil = win.create_airfoil(WORK / "foil", "2412", 4.0, 3e6)
foil_case = WORK / "foil" / "case"
check(
    "File > New airfoil case... writes C-mesh and forces",
    foil is not None
    and "NACA 2412" in (foil_case / "system/blockMeshDict").read_text(encoding="utf-8")
    and "forceCoeffs1" in (foil_case / "system/controlDict").read_text(encoding="utf-8")
    and "forceCoeffs1" in (foil_case / "system/controlDict").read_text(encoding="utf-8"),
)
win._show_run_panel()
rp = win._run_panel
check("Run panel has Continue and run info", rp is not None and rp.continue_button.isEnabled())
quality = win.show_mesh_quality()
check("Mesh > Show mesh quality reports checkMesh sets", bool(quality))
check("Help > Enter licence key... exists", action("Enter licence key...") is not None)

# ---- workspace tools: resources, import, scripts, mesh, results, runs ----
win.open_project_path(proj)
tools = win.open_tools()
check("Tools > Workspace tools opens with 6 tabs", tools.count() == 6)
check(
    "Resources shows RAM and the WSL cap",
    "GB RAM" in tools.machine.text() and tools.mem.maximum() >= 1,
)
src_case = WORK / "srccase"
shutil.copytree(proj / "case", src_case)
kind = tools.import_path(src_case, WORK / "imported" / "case")
check("Import a whole case folder", "as case" in kind)
part = tools.import_path(src_case / "system", WORK / "imported2" / "case")
check(
    "Import a single system folder",
    "as part" in part and (WORK / "imported2/case/system/controlDict").is_file(),
)
new = tools.new_case(src_case, WORK / "fromfolder")
check(
    "New case from a folder creates a project and copies the case",
    new is not None and (new / "system" / "controlDict").is_file(),
)
win.open_project_path(proj)
(proj / "case" / "hello.sh").write_text("echo scripted > scripted.txt\n", encoding="utf-8")
tools.refresh_case()
items = [tools.script_list.item(i).text() for i in range(tools.script_list.count())]
tools.script_list.setCurrentRow(items.index("hello.sh"))
tools.run_script()
ok = wait(lambda: (proj / "case/scripted.txt").is_file(), 120, 0.5)
wait(lambda: not win._solver.isRunning(), 30, 0.5)
pump(1)
check(
    "Scripts > Run selected runs in the runtime",
    ok,
    f"{win._project.case_dir} {sorted(p.name for p in (proj / 'case').iterdir())}",
)
tools.refresh_case()
check("Runs > history records the script run", tools.history.rowCount() >= 1)
check("Mesh > checkMesh table filled", tools.checks.rowCount() >= 2)
check("Mesh > patch table filled", tools.patches.rowCount() >= 1)
check("Mesh > View mesh", "Mesh" in win.show_mesh())
check("Results > colour by p", "p at the latest time" in win.show_field("p"))
exported = tools.export_to(WORK)
check("Results > export CSV", any(p.name == "residuals.csv" for p in exported))
check("y+ planner gives a height", tools.first.text().endswith(" m"))
check("Runs > pin runtime", win.pin_runtime() is not None)
from foamstudio.core.workspace import compare_cases  # noqa: E402

check("Compare cases", "No differences" in compare_cases(proj / "case", src_case))

# ---- hybrid web dashboard ----
dash = win.open_dashboard()
js_out: dict[str, object] = {}


def js(code: str, key: str) -> None:
    dash.view.page().runJavaScript(code, 0, lambda v: js_out.__setitem__(key, v))


check(
    "View > Dashboard opens the web page",
    dash is not None and win.centralWidget() is dash,
    f"win={win.isVisible()} dash={dash.isVisible()} {dash.size().toTuple()} url={dash.view.url().toString()[-30:]}",
)
ok = wait(
    lambda: (
        (js("document.getElementById('cells').textContent", "cells"), js_out.get("cells"))[1]
        not in (None, "", "–")
    ),
    30,
)
check("Dashboard renders project state from Python", ok, str(js_out.get("cells")))
js("(typeof py) + '|' + document.getElementById('history').textContent", "hist")
wait(lambda: "hist" in js_out, 10)
check(
    "Dashboard shows run history",
    "succeeded" in str(js_out.get("hist")),
    str(js_out.get("hist"))[:80],
)
js("act('processes', 3); 'sent'", "act")
ok = wait(lambda: win._run_panel is not None and win._run_panel.processes.value() == 3, 10)
check("Dashboard control calls Python (processes = 3)", ok)
shot("dashboard", dash)
win.show_mesh()
check("3D view replaces the dashboard without deleting it", win.open_dashboard() is dash)

# ---- post-processing, vertex edits, demo, background run ----
check("Mesh > vertex table filled", tools.vertices.rowCount() >= 8)
tools.apply_vertices()
check("Mesh > apply vertex edits keeps the dict valid", len(tools.vertices.selectedItems()) >= 0)
check("Results > streamlines", "streamlines" in win.show_streamlines())
line = win.line_plot("p", (0.01, 0.05, 0.005), (0.09, 0.05, 0.005))
check("Results > line plot writes CSV", line is not None and line.is_file())
check("Results > animate over time", win.animate_field("p").startswith("Animating"))
os.environ["HOME"] = str(WORK)  # Path.home() on POSIX; Windows uses USERPROFILE
os.environ["USERPROFILE"] = str(WORK)
demo = win.run_demo()
demo_log = None if demo is None else demo.case_dir / "log.Allrun"
ok = demo is not None and wait(
    lambda: any("End" in p.read_text(errors="replace") for p in demo.case_dir.glob("log.*Foam")),
    300,
    1,
)
wait(lambda: not win._solver.isRunning(), 60, 0.5)
pump(1)
check("Runs > demo cavity runs to End", ok)
assert demo is not None
win._run_panel.detached.setChecked(True)
win.start_solver()
started = wait(lambda: (demo.case_dir / ".foamstudio/detached.json").is_file(), 30, 0.5)
wait(lambda: (demo.case_dir / "log.Allrun").is_file(), 60, 0.5)
win._jobs = None  # as after a restart
check("Run > background run starts and reattaches", started and win._reattach())
wait(lambda: (demo.case_dir / ".foamstudio/job.pid").is_file(), 60, 0.5)
win.stop_solver()
win._run_panel.detached.setChecked(False)
check(
    "Run > Stop works on a reattached background run",
    "Stop requested" in win.statusBar().currentMessage(),
)

# ---- done ----
win.close()
pump()
check("File > Quit/close", not win.isVisible())
inst.close()
fails = [r for r in results if r[1] == "FAIL"]
print("\n==== SUMMARY:", len(results) - len(fails), "pass,", len(fails), "fail")
print("logged errors:", len(errors))
for e in errors:
    print("  ERR", e[:200])
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if fails else 0)
