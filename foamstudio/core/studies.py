"""Multi-run studies and their post-processing: pump curves, DOE sweeps, optimisation, acoustics,
mesh-quality histograms. Pure Python (numpy only)."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

G0 = 9.80665


# ------------------------------------------------------------------ pumps and turbines
def pump_point(dpt: float, torque: float, rpm: float, q: float, rho: float) -> dict[str, float]:
    """One operating point from CFD: total-pressure rise (Pa), shaft torque (N m), flow (m3/s)."""
    omega = rpm * 2 * math.pi / 60
    hydraulic = dpt * q
    shaft = abs(torque) * omega
    head = dpt / (rho * G0)
    ns = omega * math.sqrt(q) / (G0 * head) ** 0.75 if head > 0 else float("nan")
    return {
        "Q": q,
        "H": head,
        "P_shaft": shaft,
        "eta": hydraulic / shaft if shaft else float("nan"),
        "Ns": ns,
    }


def last_value(dat: Path, column: int = 1) -> float:
    """Last numeric row of an OpenFOAM postProcessing .dat (handles '(a b c)' vectors)."""
    for line in reversed(dat.read_text().splitlines()):
        if line and not line.startswith("#"):
            vals = line.replace("(", " ").replace(")", " ").split()
            return float(vals[column])
    raise ValueError(f"No data in {dat}")


def flow_sweep(
    q_design: float, fractions: Sequence[float] = (0.4, 0.6, 0.8, 1.0, 1.2)
) -> list[float]:
    return [q_design * f for f in fractions]


def cavitation_sweep(
    p_in: float, p_vap: float, rho: float, steps: int = 8
) -> list[tuple[float, float]]:
    """(inlet pressure, NPSH available) from p_in down to just above vapour pressure."""
    out = []
    for k in range(steps):
        p = p_vap + (p_in - p_vap) * (1 - k / steps)
        out.append((p, (p - p_vap) / (rho * G0)))
    return out


def npsh_required(points: list[tuple[float, float]], drop: float = 0.03) -> float | None:
    """NPSH at which head first falls by `drop` (3% criterion). points: (NPSHa, head), any order."""
    pts = sorted(points, reverse=True)
    h0 = pts[0][1]
    for (n1, h1), (n2, h2) in zip(pts, pts[1:], strict=False):
        if h2 <= (1 - drop) * h0 < h1:
            return n1 + (n2 - n1) * ((1 - drop) * h0 - h1) / (h2 - h1)
    return None


# ------------------------------------------------------------------ design of experiments
def latin_hypercube(
    bounds: dict[str, tuple[float, float]], n: int, seed: int = 1
) -> list[dict[str, float]]:
    rng = random.Random(seed)
    cols = {}
    for name, (lo, hi) in bounds.items():
        cells = [(k + rng.random()) / n for k in range(n)]
        rng.shuffle(cells)
        cols[name] = [lo + c * (hi - lo) for c in cells]
    return [{k: cols[k][i] for k in bounds} for i in range(n)]


def slurm_array(case_root: str, n: int, solver: str, cores: int, hours: int = 4) -> str:
    """sbatch script running case_0..case_{n-1} as a job array (one OpenFOAM case per task)."""
    return f"""#!/bin/bash
#SBATCH --job-name=foamstudio-doe
#SBATCH --array=0-{n - 1}
#SBATCH --ntasks={cores}
#SBATCH --time={hours}:00:00
cd {case_root}/case_${{SLURM_ARRAY_TASK_ID}}
decomposePar -force > log.decompose 2>&1
srun {solver} -parallel > log.solver 2>&1
reconstructPar -latestTime > log.reconstruct 2>&1
"""


def response_surface(
    xs: list[dict[str, float]], ys: list[float]
) -> Callable[[dict[str, float]], float]:
    """Quadratic least-squares fit (with cross terms) for a DOE; returns a predictor."""
    names = list(xs[0])

    def feats(x: dict[str, float]) -> list[float]:
        v = [x[n] for n in names]
        return [1.0, *v, *[a * b for i, a in enumerate(v) for b in v[i:]]]

    A = np.array([feats(x) for x in xs])
    coef, *_ = np.linalg.lstsq(A, np.array(ys), rcond=None)
    return lambda x: float(np.dot(feats(x), coef))


def nelder_mead(
    f: Callable[[list[float]], float],
    x0: list[float],
    step: float = 0.1,
    iters: int = 60,
    tol: float = 1e-6,
) -> tuple[list[float], float]:
    """Derivative-free minimiser for expensive CFD objectives (each f call = one run)."""
    n = len(x0)
    pts = [list(x0)] + [[x0[j] + (step if j == i else 0) for j in range(n)] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = sorted(range(n + 1), key=vals.__getitem__)
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < tol:
            break
        c = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        refl = [c[j] + (c[j] - pts[-1][j]) for j in range(n)]
        fr = f(refl)
        if fr < vals[0]:
            exp = [c[j] + 2 * (c[j] - pts[-1][j]) for j in range(n)]
            fe = f(exp)
            pts[-1], vals[-1] = (exp, fe) if fe < fr else (refl, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = refl, fr
        else:
            con = [c[j] + 0.5 * (pts[-1][j] - c[j]) for j in range(n)]
            fc = f(con)
            if fc < vals[-1]:
                pts[-1], vals[-1] = con, fc
            else:
                pts = [pts[0]] + [
                    [pts[0][j] + 0.5 * (p[j] - pts[0][j]) for j in range(n)] for p in pts[1:]
                ]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
    best = min(range(n + 1), key=vals.__getitem__)
    return pts[best], vals[best]


# ------------------------------------------------------------------ acoustics
def spl_spectrum(
    t: Sequence[float], p: Sequence[float], p_ref: float = 2e-5
) -> tuple[np.ndarray, np.ndarray]:
    """Narrow-band sound pressure level (dB) from a pressure probe history (resampled uniform)."""
    ta, pa = np.asarray(t, float), np.asarray(p, float)
    tu = np.linspace(ta[0], ta[-1], len(ta))
    pu = np.interp(tu, ta, pa)
    pu = (pu - pu.mean()) * np.hanning(len(pu))
    amp = np.abs(np.fft.rfft(pu)) * 2 / (len(pu) * 0.5)
    f = np.fft.rfftfreq(len(pu), tu[1] - tu[0])
    return f[1:], 20 * np.log10(np.maximum(amp[1:] / math.sqrt(2), 1e-30) / p_ref)


def oaspl(t: Sequence[float], p: Sequence[float], p_ref: float = 2e-5) -> float:
    pp = np.asarray(p, float) - np.mean(p)
    return 20 * math.log10(max(math.sqrt(float(np.mean(pp * pp))), 1e-30) / p_ref)


# ------------------------------------------------------------------ mesh quality
TARGETS = {"nonOrtho": 65.0, "skewness": 4.0, "aspectRatio": 1000.0}
ANSA = {"hex_fraction": 0.98, "aspectRatio": 2.0, "skewness": 0.5}  # FoamStudio author's targets


def histogram(
    values: Sequence[float] | np.ndarray, bins: int = 20
) -> tuple[list[float], list[int]]:
    counts, edges = np.histogram(np.asarray(values, float), bins=bins)
    return edges.tolist(), counts.tolist()


def quality_report(
    fields: dict[str, Sequence[float]], cell_types: Sequence[int] | None = None
) -> dict[str, Any]:
    """fields from `checkMesh -writeAllFields` (nonOrthoAngle, skewness, aspectRatio)."""
    rep: dict[str, Any] = {}
    for name, vals in fields.items():
        a = np.asarray(vals, float)
        rep[name] = {
            "max": float(a.max()),
            "mean": float(a.mean()),
            "p99": float(np.percentile(a, 99)),
            "hist": histogram(a),
        }
    if cell_types is not None:
        ct = np.asarray(cell_types)
        rep["hex_fraction"] = float(np.mean(ct == 12))  # VTK_HEXAHEDRON
    rep["pass"] = {k: bool(rep[k]["max"] <= v) for k, v in TARGETS.items() if k in rep}
    return rep
