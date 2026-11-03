"""Initialise a nozzle case with the 1-D isentropic flow inside the nozzle and still ambient outside.

    python scripts/nozzle_init.py CASE        (needs CASE/0/C from `postProcess -func writeCellCentres -time 0`)

The transient then starts from an established nozzle flow and shows the plume start-up into
still air, instead of an in-nozzle starting shock (which drove internal energy negative in the bell).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import nozzle_cfd as nz  # noqa: E402


def read_centres(path: Path) -> np.ndarray:
    text = path.read_text()
    body = text[text.index("internalField") :]
    n = int(re.search(r"nonuniform List<vector>\s*(\d+)", body).group(1))
    vals = re.findall(
        r"\(([-\deE.+]+) ([-\deE.+]+) ([-\deE.+]+)\)", body[: body.index("boundaryField")]
    )
    a = np.array(vals[:n], dtype=float)
    assert len(a) == n, (len(a), n)
    return a


def set_internal(path: Path, values: list[str], kind: str) -> None:
    text = path.read_text()
    field = (
        f"internalField   nonuniform List<{kind}>\n{len(values)}\n(\n"
        + "\n".join(values)
        + "\n)\n;\n"
    )
    text = re.sub(r"internalField\s+uniform[^;]*;", lambda _m: field, text, count=1)
    path.write_text(text, newline="\n")


def main(case: Path) -> None:
    m = json.loads((case / "case-meta.json").read_text())
    g, R, p0, T0 = m["gamma"], m["R"], m["p0"], m["T0"]
    contour = np.loadtxt(case / "contour.csv", delimiter=",", skiprows=1)
    xt = contour[np.argmin(contour[:, 1]), 0]
    rt = contour[:, 1].min()
    C = read_centres(case / "0" / "C")
    x, r = C[:, 0], np.hypot(C[:, 1], C[:, 2])
    rw = np.interp(x, contour[:, 0], contour[:, 1])
    inside = (x < m["x_exit"]) & (r < rw)  # exterior still-air cells stay ambient
    p = np.full(len(x), m["p_amb"])
    T = np.full(len(x), 300.0)
    U = np.zeros((len(x), 3))
    cache: dict[tuple[int, bool], float] = {}
    for i in np.flatnonzero(inside):
        eps = (rw[i] / rt) ** 2
        sup = x[i] > xt
        key = (int(eps * 2000), sup)
        if key not in cache:
            cache[key] = nz.mach_from_area(max(eps, 1.0 + 1e-6), g, supersonic=sup)
        M = cache[key]
        Ti = T0 / (1 + (g - 1) / 2 * M * M)
        p[i] = p0 * nz.p_ratio(M, g)
        T[i] = Ti
        U[i, 0] = M * np.sqrt(g * R * Ti)
    set_internal(case / "0" / "p", [f"{v:.8g}" for v in p], "scalar")
    set_internal(case / "0" / "T", [f"{v:.8g}" for v in T], "scalar")
    set_internal(case / "0" / "U", [f"({a:.8g} {b:.8g} {c:.8g})" for a, b, c in U], "vector")
    print(
        f"initialised {inside.sum()} nozzle cells of {len(x)}; exit M {U[inside, 0].max() / np.sqrt(g * R * T[inside].min()):.2f}"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
