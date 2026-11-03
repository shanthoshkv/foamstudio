"""Tools > Physics & templates: advanced physics set-up written into the open case.

Each tab is a small form; values go through foamstudio.core.physics / templates / studies, so
everything here is also scriptable from the Python console.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from foamstudio.core import physics as P
from foamstudio.core import studies as S
from foamstudio.core import templates as T


def _vec(text: str) -> tuple[float, float, float]:
    parts = [float(v) for v in text.replace(",", " ").split()]
    if len(parts) != 3:
        raise ValueError(f"Need three numbers, got {text!r}")
    return parts[0], parts[1], parts[2]


class _Form(QWidget):
    """Label/field rows + one action button. fields: (key, label, default, choices|None)."""

    def __init__(
        self,
        fields: list[tuple[Any, ...]],
        button: str,
        action: Callable[[dict[str, str]], str],
        out: QPlainTextEdit,
    ) -> None:
        super().__init__()
        self._inputs: dict[str, QLineEdit | QComboBox] = {}
        form = QFormLayout(self)
        for key, label, default, *choices in fields:
            w: QLineEdit | QComboBox
            if choices and choices[0]:
                w = QComboBox()
                w.addItems(choices[0])
                w.setCurrentText(str(default))
            else:
                w = QLineEdit(str(default))
            w.setObjectName(f"phys_{key}")
            self._inputs[key] = w
            form.addRow(label, w)
        run = QPushButton(button)
        run.clicked.connect(lambda _c=False: self._go(action, out))
        form.addRow(run)

    def values(self) -> dict[str, str]:
        return {
            k: (w.currentText() if isinstance(w, QComboBox) else w.text().strip())
            for k, w in self._inputs.items()
        }

    def _go(self, action: Callable[[dict[str, str]], str], out: QPlainTextEdit) -> None:
        try:
            out.appendPlainText(action(self.values()))
        except Exception as exc:  # noqa: BLE001 - shown to the user, not swallowed
            out.appendPlainText(f"ERROR: {exc}")


class PhysicsWindow(QDialog):
    def __init__(self, host: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.host = host
        self.setObjectName("physicsWindow")
        self.setWindowTitle(self.tr("Physics & templates"))
        self.resize(900, 680)
        self.out = QPlainTextEdit(readOnly=True)
        self.out.setObjectName("physicsLog")
        tabs = QTabWidget()
        tabs.setObjectName("physicsTabs")
        tabs.addTab(self._templates(), self.tr("Templates"))
        tabs.addTab(self._rotation(), self.tr("Rotating machinery"))
        tabs.addTab(self._boundaries(), self.tr("Boundary presets"))
        tabs.addTab(self._turbulence(), self.tr("Turbulence"))
        tabs.addTab(self._selections(), self.tr("Named selections"))
        tabs.addTab(self._initial(), self.tr("Initial fields"))
        tabs.addTab(self._mesh(), self.tr("Mesh layers & quality"))
        tabs.addTab(self._analysis(), self.tr("Analysis outputs"))
        tabs.addTab(self._studies(), self.tr("Studies & optimisation"))
        tabs.addTab(self._extend(), self.tr("Plugins & solvers"))
        layout = QVBoxLayout(self)
        layout.addWidget(tabs, 3)
        layout.addWidget(QLabel(self.tr("Output")))
        layout.addWidget(self.out, 1)

    # ---- helpers
    def _case(self) -> Path:
        project = getattr(self.host, "_project", None)
        if project is None:
            raise ValueError("Open or create a project first (File > New project).")
        return Path(project.case_dir)

    def _write(self, rel: str, text: str) -> str:
        path = P.write(self._case(), rel, text)
        return f"Wrote {path}"

    def _form(
        self, fields: list[tuple[Any, ...]], button: str, action: Callable[[dict[str, str]], str]
    ) -> _Form:
        return _Form(fields, button, action, self.out)

    # ---- tabs
    def _templates(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.template_list = QListWidget()
        self.template_list.setObjectName("templateList")
        for t in T.TEMPLATES:
            self.template_list.addItem(f"{t.title}  -  {t.physics}")
        go = QPushButton(self.tr("Create project from template..."))
        go.clicked.connect(lambda _c=False: self._from_template())
        lay.addWidget(
            QLabel(
                self.tr(
                    "Validated OpenFOAM tutorials, copied into a new project and ready to edit."
                )
            )
        )
        lay.addWidget(self.template_list)
        lay.addWidget(go)
        return page

    def _from_template(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        row = self.template_list.currentRow()
        if row < 0:
            self.out.appendPlainText("Pick a template first.")
            return
        runtime = self.host._store.load_runtime()
        if runtime is None:
            self.out.appendPlainText("No runtime saved: Tools > Setup and libraries.")
            return
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("New project folder"), self.host._projects_root()
        )
        if not folder:
            return
        try:
            project = self.host.create_project(Path(folder))
            if project is None:
                raise RuntimeError("Could not create the project (see the log).")
            case = T.copy_template(runtime, T.TEMPLATES[row].key, Path(project.root))
            self.out.appendPlainText(
                f"Template copied to {case}. Run its Allrun from Tools > Scripts."
            )
        except Exception as exc:  # noqa: BLE001
            self.out.appendPlainText(f"ERROR: {exc}")

    def _rotation(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(
            QLabel(
                self.tr(
                    "Rotor region as a box cellZone, then a rotating frame (steady) or a "
                    "sliding mesh (transient, needs cyclicAMI interfaces)."
                )
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("zone", "Zone name", "rotor"),
                    ("lo", "Box min (x y z)", "-0.1 -0.1 -0.1"),
                    ("hi", "Box max (x y z)", "0.1 0.1 0.1"),
                ],
                self.tr("Write rotor cellZone (topoSetDict)"),
                lambda v: (
                    self._write(
                        "system/topoSetDict",
                        P.cell_zone_box(v["zone"], _vec(v["lo"]), _vec(v["hi"])),
                    )
                    + "\nRun: topoSet"
                ),
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("zone", "Zone", "rotor"),
                    ("origin", "Origin", "0 0 0"),
                    ("axis", "Axis", "0 0 1"),
                    ("rpm", "Speed (rpm)", "35000"),
                    ("mode", "Method", "MRF (steady)", ["MRF (steady)", "Sliding mesh"]),
                    ("fixed", "Non-rotating patches", ""),
                ],
                self.tr("Write rotation"),
                self._rotate,
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("patch", "Wall patch", "impeller"),
                    ("origin", "Origin", "0 0 0"),
                    ("axis", "Axis", "0 0 1"),
                    ("rpm", "Speed (rpm)", "35000"),
                ],
                self.tr("Show rotating-wall U entry"),
                lambda v: (
                    f"0/U boundaryField:\n    {v['patch']}\n    "
                    + P.rotating_wall(_vec(v["origin"]), _vec(v["axis"]), float(v["rpm"]))
                ),
            )
        )
        return page

    def _rotate(self, v: dict[str, str]) -> str:
        o, a, rpm = _vec(v["origin"]), _vec(v["axis"]), float(v["rpm"])
        if v["mode"].startswith("MRF"):
            return self._write(
                "constant/MRFProperties", P.mrf(v["zone"], o, a, rpm, v["fixed"].split())
            )
        msg = self._write("constant/dynamicMeshDict", P.solid_body_rotation(v["zone"], o, a, rpm))
        return (
            msg
            + "\nNext: split the rotor interface into a cyclicAMI pair (createBaffles), see the AMI template."
        )

    def _boundaries(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(
            QLabel(
                self.tr(
                    "Entries to paste into 0/p, 0/T, 0/U. Atmosphere uses US Standard Atmosphere 1976."
                )
            )
        )
        lay.addWidget(
            self._form(
                [
                    (
                        "kind",
                        "Preset",
                        "atmosphere",
                        ["atmosphere", "rocket", "tunnel", "massflow", "ramp"],
                    ),
                    ("args", "Values (key=value ...)", "h=10000 mach=0.8"),
                ],
                self.tr("Make entries"),
                lambda v: "\n".join(
                    f"{f}: {e}"
                    for f, e in P.preset_entries(
                        v["kind"],
                        **{k: float(x) for k, x in (a.split("=") for a in v["args"].split())},
                    ).items()
                ),
            )
        )
        lay.addWidget(
            self._form(
                [("h", "Altitude (m)", "0")],
                self.tr("Atmosphere at altitude"),
                lambda v: "T {:.2f} K, p {:.1f} Pa, rho {:.4f} kg/m3, a {:.1f} m/s".format(
                    *P.isa(float(v["h"]))
                ),
            )
        )
        lay.addWidget(
            self._form(
                [("expr", "Expression", "10*sin(2*pi()*5*time())")],
                self.tr("Expression BC entry"),
                lambda v: P.expression_bc(v["expr"]),
            )
        )
        return page

    def _turbulence(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        models = ["laminar", *sorted(P.RAS), *sorted(P.LES)]
        lay.addWidget(
            self._form(
                [("model", "Model", "kOmegaSST", models)],
                self.tr("Write momentumTransport"),
                lambda v: (
                    self._write("constant/momentumTransport", P.turbulence(v["model"]))
                    + "\n"
                    + self._write("constant/turbulenceProperties", P.turbulence(v["model"]))
                ),
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("U", "Speed (m/s)", "50"),
                    ("I", "Intensity", "0.05"),
                    ("L", "Length scale (m)", "0.01"),
                ],
                self.tr("Inlet turbulence values"),
                lambda v: json.dumps(
                    P.turbulence_inlet(float(v["U"]), float(v["I"]), float(v["L"])), indent=1
                ),
            )
        )
        return page

    def _selections(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(
            QLabel(
                self.tr(
                    "Name a group of boundary faces, then make it a patch (for BCs) or a faceZone. "
                    "Pick in 3D: the 3D view's 'Pick faces' fills the box from your selection."
                )
            )
        )
        self.sel_form = self._form(
            [
                ("name", "Name", "inletLip"),
                ("kind", "Select by", "box", ["box", "cylinder", "sphere", "normal", "patch"]),
                ("a", "Box min / p1 / origin / normal / patch", "0 0 0"),
                ("b", "Box max / p2", "1 1 1"),
                ("radius", "Radius or cos", "0.1"),
                ("within", "Only inside patch (optional)", ""),
                ("as", "Make", "patch", ["patch", "wall patch", "faceZone"]),
            ],
            self.tr("Write topoSet + createPatch"),
            self._select,
        )
        lay.addWidget(self.sel_form)
        return page

    def _select(self, v: dict[str, str]) -> str:
        sel: dict[str, Any] = {
            "name": v["name"],
            "kind": v["kind"],
            "within": v["within"] or None,
            "zone": v["as"] == "faceZone",
        }
        k = v["kind"]
        if k == "box":
            sel.update(min=_vec(v["a"]), max=_vec(v["b"]))
        elif k == "cylinder":
            sel.update(p1=_vec(v["a"]), p2=_vec(v["b"]), radius=float(v["radius"]))
        elif k == "sphere":
            sel.update(origin=_vec(v["a"]), radius=float(v["radius"]))
        elif k == "normal":
            sel.update(normal=_vec(v["a"]), cos=float(v["radius"]))
        else:
            sel.update(patch=v["a"])
        msg = self._write("system/topoSetDict", P.topo_set([sel]))
        if v["as"] != "faceZone":
            msg += "\n" + self._write(
                "system/createPatchDict",
                P.create_patch([v["name"]], "wall" if v["as"] == "wall patch" else "patch"),
            )
            return msg + "\nRun: topoSet && createPatch -overwrite"
        return msg + "\nRun: topoSet"

    def set_pick_box(self, lo: tuple[float, float, float], hi: tuple[float, float, float]) -> None:
        """Called by the 3D view after an interactive pick."""
        self.sel_form._inputs["kind"].setCurrentText("box")  # type: ignore[union-attr]
        self.sel_form._inputs["a"].setText(" ".join(f"{x:.6g}" for x in lo))  # type: ignore[union-attr]
        self.sel_form._inputs["b"].setText(" ".join(f"{x:.6g}" for x in hi))  # type: ignore[union-attr]

    def _initial(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(
            self._form(
                [
                    ("field", "Field", "alpha.water"),
                    ("default", "Default value", "0"),
                    ("value", "Value in box", "1"),
                    ("lo", "Box min", "0 0 -1"),
                    ("hi", "Box max", "0.15 0.3 1"),
                ],
                self.tr("Write setFieldsDict"),
                lambda v: (
                    self._write(
                        "system/setFieldsDict",
                        P.set_fields(
                            {v["field"]: v["default"]},
                            [
                                {
                                    "box": (_vec(v["lo"]), _vec(v["hi"])),
                                    "values": {v["field"]: v["value"]},
                                }
                            ],
                        ),
                    )
                    + "\nRun: setFields"
                ),
            )
        )
        lay.addWidget(
            QLabel(
                self.tr(
                    "Map a coarse solution onto this mesh: mapFields <sourceCase> -consistent -sourceTime latestTime"
                )
            )
        )
        return page

    def _mesh(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(
            self._form(
                [
                    ("yplus", "Target y+", "1"),
                    ("U", "Speed (m/s)", "50"),
                    ("L", "Length (m)", "1"),
                    ("nu", "nu (m2/s)", "1.5e-5"),
                    ("n", "Layers", "15"),
                    ("g", "Growth", "1.2"),
                    ("patches", "Patches", "wall"),
                ],
                self.tr("Boundary-layer controls"),
                self._layers,
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("stl", "STL file (in constant/triSurface)", "part.stl"),
                    ("size", "Max cell (m)", "0.05"),
                    ("layers", "Layers", "3"),
                ],
                self.tr("Write cfMesh meshDict"),
                lambda v: (
                    self._write(
                        "system/meshDict",
                        P.cfmesh(v["stl"], float(v["size"]), layers=int(v["layers"])),
                    )
                    + "\nRun: cartesianMesh"
                ),
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("field", "Indicator field", "magGradRho"),
                    ("lo", "Refine above", "50"),
                    ("level", "Max level", "2"),
                ],
                self.tr("Adaptive refinement"),
                lambda v: self._write(
                    "constant/dynamicMeshDict",
                    P.adaptive_refinement(v["field"], float(v["lo"]), 1e30, int(v["level"])),
                ),
            )
        )
        btn = QPushButton(self.tr("Mesh quality report (checkMesh -writeAllFields)"))
        btn.clicked.connect(lambda _c=False: self._quality())
        lay.addWidget(btn)
        return page

    def _layers(self, v: dict[str, str]) -> str:
        first = P.first_layer(float(v["yplus"]), float(v["U"]), float(v["L"]), float(v["nu"]))
        block = P.layer_controls(int(v["n"]), first, float(v["g"]), v["patches"].split())
        return f"First layer {first:.3g} m for y+ {v['yplus']}.\nPaste into snappyHexMeshDict:\n{block}"

    def _quality(self) -> None:
        try:
            self.host.run_command("checkMesh -writeAllFields -latestTime", "checkMeshFields")
            self.out.appendPlainText(
                "checkMesh running; when it ends, Results > colour by nonOrthoAngle or skewness. "
                f"Targets: {S.TARGETS}; strict hex-mesh targets: {S.ANSA}"
            )
        except Exception as exc:  # noqa: BLE001
            self.out.appendPlainText(f"ERROR: {exc}")

    def _analysis(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(
            self._form(
                [
                    ("which", "Outputs (space separated)", "schlieren Q yPlus forces"),
                    ("patches", "Force/torque patches", "wall"),
                    ("rho", "rhoInf (incompressible)", "1000"),
                    ("inlet", "Pump inlet patch", "inlet"),
                    ("outlet", "Pump outlet patch", "outlet"),
                ],
                self.tr("Write function objects"),
                lambda v: (
                    self._write(
                        "system/foamstudioFunctions",
                        P.function_objects(
                            v["which"].split(),
                            wrapped=False,
                            patches=v["patches"].split(),
                            rhoInf=float(v["rho"]),
                            inlet=v["inlet"],
                            outlet=v["outlet"],
                        ),
                    )
                    + '\nThe next run adds #include "foamstudioFunctions" inside controlDict\'s functions block.'
                ),
            )
        )
        return page

    def _studies(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(
            self._form(
                [
                    ("dpt", "Total-pressure rise (Pa)", "1.75e7"),
                    ("torque", "Torque (N m)", "1500"),
                    ("rpm", "Speed (rpm)", "35000"),
                    ("q", "Flow (m3/s)", "0.124"),
                    ("rho", "Density", "805"),
                ],
                self.tr("Pump operating point"),
                lambda v: json.dumps(
                    S.pump_point(
                        float(v["dpt"]),
                        float(v["torque"]),
                        float(v["rpm"]),
                        float(v["q"]),
                        float(v["rho"]),
                    ),
                    indent=1,
                ),
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("bounds", "Bounds (name=lo:hi ...)", "alpha=0:10 Re=1e6:6e6"),
                    ("n", "Runs", "8"),
                ],
                self.tr("Latin hypercube plan"),
                lambda v: json.dumps(
                    S.latin_hypercube(
                        {
                            k: (float(r.split(":")[0]), float(r.split(":")[1]))
                            for k, r in (b.split("=") for b in v["bounds"].split())
                        },
                        int(v["n"]),
                    ),
                    indent=1,
                ),
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("root", "Cases root (on cluster)", "~/doe"),
                    ("n", "Runs", "8"),
                    ("solver", "Solver", "simpleFoam"),
                    ("cores", "Cores", "16"),
                ],
                self.tr("SLURM job-array script"),
                lambda v: S.slurm_array(v["root"], int(v["n"]), v["solver"], int(v["cores"])),
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("cells", "Cells", "200000"),
                    ("steps", "Steps", "50000"),
                    ("cores", "Cores", "8"),
                    ("us", "us/cell-step", "2.5"),
                    ("price", "Price per core-hour", "0.05"),
                ],
                self.tr("Run time and cost estimate"),
                lambda v: json.dumps(
                    P.run_cost(
                        int(float(v["cells"])),
                        int(float(v["steps"])),
                        int(v["cores"]),
                        float(v["us"]),
                        float(v["price"]),
                    ),
                    indent=1,
                ),
            )
        )
        lay.addWidget(
            self._form(
                [
                    ("f1", "Fine-mesh value", "0.999100"),
                    ("f2", "Medium", "0.999013"),
                    ("f3", "Coarse", "0.998215"),
                    ("r", "Refinement ratio", "2"),
                ],
                self.tr("Grid convergence (GCI)"),
                lambda v: "observed order {:.2f}, extrapolated {:.6g}, GCI_fine {:.3%}".format(
                    *P.gci(float(v["f1"]), float(v["f2"]), float(v["f3"]), float(v["r"]))
                ),
            )
        )
        return page

    def _extend(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        found = T.plugins()
        lay.addWidget(QLabel(self.tr("Plugins folder: %1").replace("%1", str(T.plugin_dir()))))
        lst = QListWidget()
        for p in found:
            lst.addItem(f"{p.get('name')}  -  {p.get('description', '')}")
        if not found:
            lst.addItem(
                self.tr(
                    "No plugins. A plugin is a folder with plugin.json {name, description, template, script}."
                )
            )
        lay.addWidget(lst)
        row = QHBoxLayout()
        for name in T.PATCHES:
            b = QPushButton(self.tr("Build patched solver: %1").replace("%1", name))
            b.clicked.connect(lambda _c=False, n=name: self._build(n))
            row.addWidget(b)
        lay.addLayout(row)
        return page

    def _build(self, name: str) -> None:
        runtime = self.host._store.load_runtime()
        if runtime is None:
            self.out.appendPlainText("No runtime saved.")
            return
        root = Path(__file__).resolve().parents[2]
        self.out.appendPlainText(T.build_patched_solver(runtime, name, root))
