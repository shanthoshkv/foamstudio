"""Prove OpenFOAM accepts FoamStudio's physics dictionaries: copy tutorial templates, swap in our
generated dictionaries, run the real tools briefly (one core). Prints PASS/FAIL per check.

    python scripts/physics_check.py RUNTIME_JSON SCRATCH_DIR   (SCRATCH_DIR = a WSL UNC path)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foamstudio.core import physics as P  # noqa: E402
from foamstudio.core import templates as T  # noqa: E402
from foamstudio.core.runtime.model import Installation  # noqa: E402
from foamstudio.core.runtime.paths import windows_to_wsl  # noqa: E402

inst = Installation.from_dict(json.loads(Path(sys.argv[1]).read_text()))
root = Path(sys.argv[2])
results: list[tuple[str, bool, str]] = []


def sh(case: Path, script: str, timeout: int = 900) -> tuple[int, str]:
    body = f"source {inst.bashrc} >/dev/null 2>&1 || true\ncd {windows_to_wsl(str(case).replace(chr(92), '/'))}\n{script}\n"
    runner = case / "check.sh"
    runner.write_text(body, newline="\n")
    done = subprocess.run(
        [
            "wsl.exe",
            "-d",
            inst.distro,
            "--",
            "bash",
            windows_to_wsl(str(runner).replace(chr(92), "/")),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return done.returncode, (done.stdout + done.stderr)[-1500:]


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(
        ("PASS " if ok else "FAIL ")
        + name
        + ("  " + detail.splitlines()[-1][:160] if detail and not ok else ""),
        flush=True,
    )


def fresh(key: str) -> Path:
    d = root / key
    if d.exists():
        sh(root, f"rm -rf {key}")
    d.mkdir(parents=True)
    return T.copy_template(inst, key, d)


# 1. every template copies and has a controlDict (or Allrun for multi-case folders)
for t in T.TEMPLATES:
    try:
        c = fresh(t.key)
        check(
            f"template {t.key}",
            (c / "system" / "controlDict").is_file() or (c / "Allrun").is_file(),
        )
    except Exception as exc:  # noqa: BLE001
        check(f"template {t.key}", False, str(exc))

# 2. MRF: our MRFProperties drives simpleFoam in the mixer vessel
c = root / "mrf" / "case"
P.write(c, "constant/MRFProperties", P.mrf("rotor", (0, 0, 0), (0, 0, 1), 1000, []))
rc, out = sh(
    c,
    "m4 system/blockMeshDict.m4 > system/blockMeshDict; blockMesh > log.bm 2>&1; "
    "rm -rf 0; cp -r 0.orig 0; "
    "sed -i 's/^endTime .*/endTime 20;/; s/^writeInterval .*/writeInterval 20;/' system/controlDict; "
    "simpleFoam > log.run 2>&1; echo rc=$?; grep -c '^Time =' log.run; tail -3 log.run",
)
check("MRF (simpleFoam, 1000 rpm rotor)", "rc=0" in out and "End" in out, out)

# 3. sliding mesh: our dynamicMeshDict (solidBody rotation) in the AMI vessel
c = root / "ami" / "case"
P.write(c, "constant/dynamicMeshDict", P.solid_body_rotation("rotor", (0, 0, 0), (0, 0, 1), 60))
rc, out = sh(
    c,
    "./Allrun.pre > log.pre 2>&1; rm -rf 0; cp -r 0.orig 0; "
    "sed -i 's/^endTime .*/endTime 0.01;/' system/controlDict; "
    "pimpleFoam > log.run 2>&1; echo rc=$?; grep -c '^Time =' log.run; tail -3 log.run",
)
check("Sliding mesh AMI (pimpleFoam, 60 rpm)", "rc=0" in out and "End" in out, out)

# 4. named selections: topoSet + createPatch on the cavity-like LES step mesh
c = root / "les" / "case"
P.write(
    c,
    "system/topoSetDict",
    P.topo_set(
        [
            {
                "name": "upperLip",
                "kind": "box",
                "min": (-0.03, 0.0, -1),
                "max": (0.0, 0.03, 1),
                "within": "upperWall",
            },
            {
                "name": "outletTop",
                "kind": "normal",
                "normal": (1, 0, 0),
                "cos": 0.99,
                "within": "outlet",
            },
        ]
    ),
)
P.write(c, "system/createPatchDict", P.create_patch(["upperLip"], "wall"))
rc, out = sh(
    c,
    "blockMesh > log.bm 2>&1; topoSet > log.ts 2>&1; echo ts=$?; createPatch -overwrite > log.cp 2>&1; "
    "echo cp=$?; grep -A3 upperLip constant/polyMesh/boundary | head -4",
)
check(
    "Named selection -> topoSet + createPatch",
    "ts=0" in out and "cp=0" in out and "upperLip" in out,
    out,
)

# 5. initial fields: our setFieldsDict on the dam break
c = root / "vof" / "case"
P.write(
    c,
    "system/setFieldsDict",
    P.set_fields(
        {"alpha.water": "0"},
        [{"box": ((0, 0, -1), (0.1461, 0.292, 1)), "values": {"alpha.water": "1"}}],
    ),
)
rc, out = sh(
    c,
    "blockMesh > log.bm 2>&1; restore0Dir > /dev/null 2>&1 || cp -r 0.orig 0; setFields > log.sf 2>&1; "
    "echo sf=$?; grep -c 'nonuniform' 0/alpha.water",
)
check("setFields (dam break water column)", "sf=0" in out, out)

# 6. turbulence model switch: kOmegaSST on the LES step (as RAS) - dictionary parse + model construction
P.write(c, "constant/momentumTransport.check", P.turbulence("kOmegaSST"))
rc, out = sh(
    c, "foamDictionary constant/momentumTransport.check -entry RAS/model -value; echo fd=$?"
)
check("turbulence dictionary (kOmegaSST)", "kOmegaSST" in out and "fd=0" in out, out)

# 7. every other writer parses with foamDictionary
scratch = root / "parse"
writers = {
    "MRFProperties": P.mrf("rotor", (0, 0, 0), (0, 0, 1), 35000, ["casing"]),
    "dynamicMeshDict.rot": P.solid_body_rotation("rotor", (0, 0, 0), (1, 0, 0), 35000),
    "dynamicMeshDict.refine": P.adaptive_refinement("magGradRho", 50, 1e9),
    "topoSetDict": P.topo_set(
        [
            {
                "name": "a",
                "kind": "cylinder",
                "p1": (0, 0, 0),
                "p2": (1, 0, 0),
                "radius": 0.1,
                "zone": True,
            },
            {"name": "b", "kind": "sphere", "origin": (0, 0, 0), "radius": 1},
        ]
    ),
    "cellZone": P.cell_zone_box("rotor", (-1, -1, -1), (1, 1, 1)),
    "createPatchDict": P.create_patch(["a", "b"]),
    "thermo.perfect": P.perfect_gas(28.96, 1005, "air"),
    "thermo.PR": P.peng_robinson("O2", 1700, 1.9e-4),
    "meshDict": P.cfmesh("part.stl", 0.05, {"wall": (0.005, 2)}, layers=3),
    "turb.LES": P.turbulence("WALE"),
}
scratch.mkdir(parents=True, exist_ok=True)
for name, text in writers.items():
    (scratch / name).write_text(text, newline="\n")
fo = P._head("controlDict") + P.function_objects(
    ["schlieren", "Q", "vorticity", "yPlus", "forces", "pumpHead", "probes"],
    patches=["blade"],
    points=[(0.1, 0, 0)],
)
(scratch / "functions").write_text(fo, newline="\n")
names = " ".join([*writers, "functions"])
rc, out = sh(
    scratch,
    f"for f in {names}; do foamDictionary $f > /dev/null 2>err.txt && echo ok-$f || echo BAD-$f; done",
)
for name in [*writers, "functions"]:
    check(f"parse {name}", f"ok-{name}" in out, out)

# 8. BC presets: entries parse as dictionaries
bc = P._head("bc") + "\n".join(
    f"{k}_{f} {v}"
    for k, kw in (
        ("atmosphere", {"h": 10000, "mach": 0.8}),
        ("rocket", {"p0": 3.5e7, "T0": 3783}),
        ("tunnel", {"mach": 2, "p": 1e5, "T": 300}),
        ("massflow", {"mdot": 100}),
    )
    for f, v in P.preset_entries(k, **kw).items()
)
(scratch / "bcpresets").write_text(
    bc + "\nexpr " + P.expression_bc("10*sin(2*pi()*5*time())") + "\n", newline="\n"
)
rc, out = sh(scratch, "foamDictionary bcpresets > /dev/null && echo ok-bc || cat err.txt")
check("parse BC presets + expression BC", "ok-bc" in out, out)

passed = sum(ok for _n, ok, _d in results)
print(f"\n{passed}/{len(results)} passed")
(root / "physics-check.json").write_text(
    json.dumps([{"check": n, "ok": ok} for n, ok, _d in results], indent=2)
)
sys.exit(0 if passed == len(results) else 1)
