"""Rerun validation samples through FoamStudio and compare with samples/*/reference.json.

    python scripts/validate.py --runtime RUNTIME_JSON --work DIR [--cases cavity,step]

Writes DIR/validation.json and prints a Markdown table. Exit 1 if any case fails.
Cases: cavity (Ghia Re=100 centreline, ~15 s), step (Driver & Seegmiller xr/h, ~5 min).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SAMPLES = REPO / "samples"
RUN = "bash ./Allrun && postProcess -func sampleDict -latestTime > log.sample 2>&1"


def foamstudio(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "foamstudio", *args], capture_output=True, text=True, cwd=REPO
    )


def prepare(name: str, spec: Path, work: Path, mesh_text: str, sample: Path) -> Path:
    project = work / name
    shutil.rmtree(project, ignore_errors=True)
    done = foamstudio("--write-case", str(spec), "--project", str(project))
    if done.returncode != 0:
        raise RuntimeError(f"--write-case failed for {name}:\n{done.stderr[-800:]}")
    system = project / "case" / "system"
    (system / "blockMeshDict").write_text(mesh_text, encoding="utf-8", newline="\n")
    shutil.copy(sample, system / "sampleDict")
    return project


def solve(project: Path, runtime: Path) -> None:
    done = foamstudio(
        "--project", str(project), "--run-case", "--command", RUN, "--runtime", str(runtime)
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"run failed for {project.name}:\n{done.stdout[-800:]}{done.stderr[-800:]}"
        )


def sample_file(project: Path, pattern: str) -> np.ndarray:
    found = sorted((project / "case" / "postProcessing" / "sampleDict").glob(f"*/{pattern}"))
    if not found:
        raise RuntimeError(f"no sample {pattern} in {project}")
    return np.loadtxt(found[-1])


def cavity(work: Path, runtime: Path) -> dict[str, object]:
    from foamstudio.core.mesh import block_mesh_dict

    ref = json.loads((SAMPLES / "cavity" / "reference.json").read_text())
    mesh = block_mesh_dict("box", length=1, height=1, width=0.1, cells=(64, 64, 1))
    project = prepare(
        "cavity", SAMPLES / "cavity" / "case.json", work, mesh, SAMPLES / "cavity" / "sampleDict"
    )
    solve(project, runtime)
    data = sample_file(project, "vertical_U.xy")  # y Ux Uy Uz
    ys = np.array([p["x"] for p in ref["series"]])
    want = np.array([p["y"] for p in ref["series"]])
    got = np.interp(ys, data[:, 0], data[:, 1])
    error = float(np.max(np.abs(got - want)))
    return {
        "case": "cavity",
        "quantity": "max abs(Ux - Ghia) on x=0.5",
        "value": round(error, 5),
        "reference": f"0 +/- {ref['tolerance']}",
        "pass": error <= ref["tolerance"],
    }


def step(work: Path, runtime: Path) -> dict[str, object]:
    base = SAMPLES / "backward-facing-step"
    ref = json.loads((base / "reference.json").read_text())
    mesh = (base / "blockMeshDict-50h").read_text()
    project = prepare("step", base / "case.json", work, mesh, base / "sampleDict")
    solve(project, runtime)
    data = sample_file(project, "near1_U.xy")  # x Ux Uy Uz, 0.3 mm above the floor
    h = 0.0127
    x, ux = data[:, 0], data[:, 1]
    crossings = [
        x[i] - ux[i] * (x[i + 1] - x[i]) / (ux[i + 1] - ux[i])
        for i in range(len(x) - 1)
        if ux[i] < 0 <= ux[i + 1]
    ]
    if not crossings:
        raise RuntimeError("no reattachment found (Ux never changes sign)")
    xr = float(crossings[-1] / h)
    return {
        "case": "backward-facing-step",
        "quantity": "reattachment xr/h",
        "value": round(xr, 3),
        "reference": f"{ref['value']} +/- {ref['tolerance']}",
        "pass": abs(xr - ref["value"]) <= ref["tolerance"],
    }


CASES = {"cavity": cavity, "step": step}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--cases", default="cavity,step")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for name in args.cases.split(","):
        try:
            rows.append(CASES[name](args.work.resolve(), args.runtime.resolve()))
        except Exception as exc:  # report and keep going: one broken case must not hide the rest
            rows.append(
                {
                    "case": name,
                    "quantity": "-",
                    "value": "-",
                    "reference": "-",
                    "pass": False,
                    "error": str(exc),
                }
            )
    (args.work / "validation.json").write_text(json.dumps(rows, indent=2) + "\n")
    print("| Case | Quantity | Value | Reference | Status |\n| --- | --- | --- | --- | --- |")
    for row in rows:
        status = "PASS" if row["pass"] else "FAIL"
        cells = [row["case"], row["quantity"], row["value"], row["reference"], status]
        print("| " + " | ".join(str(cell) for cell in cells) + " |")
        if "error" in row:
            print(f"\n{row['case']}: {row['error']}", file=sys.stderr)
    return 0 if all(row["pass"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
