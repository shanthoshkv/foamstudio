"""Parameter sweep: one case.json, one key, several values -> one project per value.

    python scripts/sweep.py --spec samples/cavity/case.json --key state.nu \\
        --values 0.01,0.0025 --runtime runtime.json --work sweep \\
        [--block-mesh box --cells 32,32,1 | --mesh-dict path/to/blockMeshDict]

Each value gets its own project (generated through the case generator, so dictionaries
stay generator-written), is meshed and run with ./Allrun through the runtime, and gets an
HTML report with provenance. A Markdown summary is printed and saved as WORK/sweep.md.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _set(spec: dict[str, object], dotted: str, value: object) -> None:
    node: object = spec
    parts = dotted.split(".")
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"{dotted}: {part!r} not found in case.json")
        node = node[part]
    if not isinstance(node, dict):
        raise KeyError(f"{dotted}: parent is not an object")
    node[parts[-1]] = value


def _parse(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _foamstudio(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "foamstudio", *args], capture_output=True, text=True, cwd=REPO
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--key", required=True, help="dotted path, e.g. state.nu")
    parser.add_argument("--values", required=True, help="comma-separated JSON values")
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    mesh = parser.add_mutually_exclusive_group(required=True)
    mesh.add_argument("--block-mesh", choices=("box", "channel", "wedge"))
    mesh.add_argument("--mesh-dict", type=Path)
    parser.add_argument("--cells", default="40,40,1", help="nx,ny,nz for --block-mesh")
    args = parser.parse_args()

    from foamstudio.core.mesh import block_mesh_dict
    from foamstudio.core.post.report import inputs_for_case, write_html

    base = json.loads(args.spec.read_text(encoding="utf-8"))
    args.work.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str, str, str]] = []
    for index, raw in enumerate(args.values.split(",")):
        value = _parse(raw.strip())
        spec = json.loads(json.dumps(base))
        _set(spec, args.key, value)
        spec["caseName"] = f"{base['caseName']}-{index}"
        project = (args.work / f"case-{index}").resolve()
        shutil.rmtree(project, ignore_errors=True)
        spec_path = args.work.resolve() / f"case-{index}.json"
        spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        done = _foamstudio("--write-case", str(spec_path), "--project", str(project))
        if done.returncode != 0:
            rows.append((str(value), "write failed", "-", done.stderr.strip().splitlines()[-1]))
            continue
        target = project / "case" / "system" / "blockMeshDict"
        if args.mesh_dict:
            shutil.copy(args.mesh_dict, target)
        else:
            cells = tuple(int(n) for n in args.cells.split(","))
            target.write_text(block_mesh_dict(args.block_mesh, cells=cells), newline="\n")  # type: ignore[arg-type]
        run = _foamstudio(
            "--project",
            str(project),
            "--run-case",
            "--command",
            "bash ./Allrun",
            "--runtime",
            str(args.runtime.resolve()),
        )
        report = inputs_for_case(f"{args.key}={value}", project / "case")
        write_html(report, project / "report.html")
        residual = "-" if report.residual_final is None else f"{report.residual_final:.3g}"
        status = "ok" if run.returncode == 0 else "run failed"
        rows.append((str(value), status, residual, str(project / "report.html")))
        print(f"{args.key}={value}: {status}", flush=True)

    lines = [
        f"| {args.key} | Status | Final residual | Report |",
        "| --- | --- | --- | --- |",
        *(f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows),
    ]
    (args.work / "sweep.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all(row[1] == "ok" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
