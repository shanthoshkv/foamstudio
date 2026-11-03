"""Post-process the nozzle cases written by nozzle_cfd.py.

python scripts/nozzle_post.py validate ROOT          -> validation table (JSON + stdout)
python scripts/nozzle_post.py raptor ROOT/raptor3-sl -> performance from the late-time solution
python scripts/nozzle_post.py frames CASE OUTDIR [--width 3840] -> PNG frames for the plume video
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import nozzle_cfd as nz  # noqa: E402

FULL = 2 * math.pi / math.sin(nz.WEDGE)  # flat wedge faces -> full annulus (not 2*pi/theta)


def _dat(path: Path) -> np.ndarray:
    rows = [ln.split() for ln in path.read_text().splitlines() if ln and not ln.startswith("#")]
    return np.array([[float(v) for v in r[:2]] for r in rows])


def mdot(case: Path, patch: str = "flowRates") -> tuple[float, float]:
    """Mean |mass flow| over the last 25% of the run (full nozzle), and its relative spread."""
    data = _dat(next((case / "postProcessing" / patch).glob("*/surfaceFieldValue.dat")))
    tail = data[data[:, 0] >= 0.75 * data[-1, 0], 1]
    return abs(tail.mean()) * FULL, float(np.ptp(tail) / abs(tail.mean()))


def _reader(case: Path):
    """Reconstructed case only (run reconstructPar first); PyVista cannot read processor dirs."""
    import pyvista as pv

    marker = case / "case.foam"
    marker.touch()
    r = pv.OpenFOAMReader(str(marker))
    r.enable_all_patch_arrays()
    return r


def outlet_thrust(case: Path, p_amb: float) -> float:
    r = _reader(case)
    r.set_active_time_value(r.time_values[-1])
    out = r.read()["boundary"]["outlet"].compute_cell_sizes(length=False, volume=False)
    p, U = out.cell_data["p"], out.cell_data["U"]
    rho = (
        out.cell_data["rho"] if "rho" in out.cell_data else p / (case_R(case) * out.cell_data["T"])
    )
    return float(np.sum((rho * U[:, 0] ** 2 + (p - p_amb)) * out.cell_data["Area"]) * FULL)


def case_R(case: Path) -> float:
    return json.loads((case / "case-meta.json").read_text())["R"]


def gci(f1: float, f2: float, f3: float, r: float = 2.0) -> tuple[float, float, float]:
    """Roache GCI on the fine grid: (observed order, extrapolated value, GCI fraction)."""
    e32, e21 = f3 - f2, f2 - f1
    if e21 == 0 or e32 / e21 <= 0:
        return float("nan"), f1, float("nan")
    p = math.log(abs(e32 / e21)) / math.log(r)
    ext = f1 + (f1 - f2) / (r**p - 1)
    return p, ext, 1.25 * abs((f1 - f2) / f1) / (r**p - 1)


def validate(root: Path) -> dict:
    out = {}
    for name in ("iso9300-R4-coarse", "iso9300-R4-medium", "iso9300-R4-fine", "iso9300-R1-medium"):
        case = root / name
        if not (case / "postProcessing").is_dir():
            continue
        m = json.loads((case / "case-meta.json").read_text())
        ideal = nz.mdot_ideal(m["p0"], m["T0"], math.pi * m["rt"] ** 2, m["gamma"], m["R"])
        md, spread = mdot(case)
        ref = nz.cd_kliegel_levine(m["Rc_over_rt"], m["gamma"])
        out[name] = {
            "Cd": md / ideal,
            "Cd_ref": ref,
            "err_pct": 100 * (md / ideal - ref) / ref,
            "mdot_spread": spread,
        }
    fine = [out.get(f"iso9300-R4-{t}", {}).get("Cd") for t in ("fine", "medium", "coarse")]
    if all(fine):
        p, ext, g = gci(*fine)
        out["gci_R4"] = {
            "order": p,
            "Cd_extrapolated": ext,
            "gci_pct": 100 * g,
            "ext_err_pct": 100
            * (ext - out["iso9300-R4-fine"]["Cd_ref"])
            / out["iso9300-R4-fine"]["Cd_ref"],
        }
    case = root / "conical15-eps4-medium"
    if (case / "postProcessing").is_dir():
        m = json.loads((case / "case-meta.json").read_text())
        At = math.pi * m["rt"] ** 2
        F = outlet_thrust(case, m["p_amb"])
        cf = F / (m["p0"] * At)
        ideal = nz.cf_ideal(m["eps"], m["gamma"], m["p0"] / m["p_amb"])
        lam = (1 + math.cos(math.radians(m["div_deg"]))) / 2
        md, _ = mdot(case)
        cd = md / nz.mdot_ideal(m["p0"], m["T0"], At, m["gamma"], m["R"])
        # momentum term scales with lambda and Cd; pressure term does not
        me = nz.mach_from_area(m["eps"], m["gamma"])
        pe = nz.p_ratio(me, m["gamma"])
        cf_p = (pe - m["p_amb"] / m["p0"]) * m["eps"]
        ref = (ideal - cf_p) * lam * cd + cf_p
        out["conical15"] = {
            "CF": cf,
            "CF_ideal_1D": ideal,
            "lambda": lam,
            "Cd": cd,
            "CF_ref": ref,
            "err_pct": 100 * (cf - ref) / ref,
        }
    (root / "validation-results.json").write_text(json.dumps(out, indent=2))
    return out


def raptor(case: Path) -> dict:
    """Thrust from the nozzle exit plane at the latest time; mass flow from the inlet patch."""
    import pyvista as pv

    m = json.loads((case / "case-meta.json").read_text())
    r = _reader(case)
    r.set_active_time_value(r.time_values[-1])
    mesh = r.read()["internalMesh"]
    xe, re = m["x_exit"], m["re"]
    line = pv.Line(
        (xe - 1e-4, 0, 0), (xe - 1e-4, re * math.cos(nz.WEDGE / 2) * 0.999, 0), resolution=400
    )
    s = line.sample(mesh)
    rr = s.points[:, 1]
    rho, u, p = s["rho"], s["U"][:, 0], s["p"]
    T = s["T"]
    a = np.sqrt(m["gamma"] * m["R"] * T)
    dA = 2 * math.pi * rr  # annulus per unit radius
    flux = rho * u * dA
    md = np.trapezoid(flux, rr)
    F = np.trapezoid((rho * u * u + p - m["p_amb"]) * dA, rr)
    Fvac = np.trapezoid((rho * u * u + p) * dA, rr)
    Me = np.trapezoid(flux * u / a, rr) / md
    md_in, spread = mdot(case)
    g0 = 9.80665
    res = {
        "time_s": float(r.time_values[-1]),
        "mdot_inlet": md_in,
        "mdot_exit": md,
        "mdot_spread": spread,
        "thrust_SL_N": F,
        "thrust_SL_tf": F / (g0 * 1000),
        "thrust_vac_tf": Fvac / (g0 * 1000),
        "Isp_SL_s": F / (md_in * g0),
        "Isp_vac_s": Fvac / (md_in * g0),
        "exit_mach_mass_avg": Me,
        "exit_p_avg_bar": float(np.trapezoid(p * dA, rr) / (math.pi * re * re) / 1e5),
        "one_d": {
            "Me": nz.mach_from_area(m["eps"], m["gamma"]),
            "mdot": nz.mdot_ideal(m["p0"], m["T0"], math.pi * m["rt"] ** 2, m["gamma"], m["R"]),
            "CEA_Isp_SL": m["cea_isp_sl_s"],
            "CEA_Me": m["cea_mach_exit"],
        },
    }
    (case / "performance.json").write_text(json.dumps(res, indent=2, default=float))
    return res


def frames(case: Path, out: Path, width: int = 3840, every: int = 1) -> None:
    """Top half Mach number, bottom half temperature, mirrored about the axis; one PNG per write."""
    import pyvista as pv

    pv.global_theme.font.color = "white"
    out.mkdir(parents=True, exist_ok=True)
    m = json.loads((case / "case-meta.json").read_text())
    r = _reader(case)
    times = [t for t in r.time_values if t > 0][::every]
    height = int(width * 9 / 16)
    contour = np.loadtxt(case / "contour.csv", delimiter=",", skiprows=1)
    wall = np.c_[contour[:, 0], contour[:, 1], np.zeros(len(contour))]
    for k, t in enumerate(times):
        png = out / f"frame_{k:05d}.png"
        if png.exists():
            continue
        r.set_active_time_value(t)
        mesh = r.read()["internalMesh"].cell_data_to_point_data()
        U = mesh["U"]
        mesh["Mach"] = np.linalg.norm(U, axis=1) / np.sqrt(m["gamma"] * m["R"] * mesh["T"])
        top = mesh.copy()
        bottom = mesh.reflect((0, 1, 0), point=(0, 0, 0))
        k = width / 1920  # font scale
        pl = pv.Plotter(off_screen=True, window_size=(width, height))
        pl.set_background("#000004")  # inferno at ambient T, so both halves share one ground
        a_top = pl.add_mesh(
            top,
            scalars="Mach",
            cmap="turbo",
            clim=(0.12, 4.8),
            below_color="#000004",
            lighting=False,
            show_scalar_bar=False,
        )
        a_bot = pl.add_mesh(
            bottom,
            scalars="T",
            cmap="inferno",
            clim=(250, 3800),
            lighting=False,
            show_scalar_bar=False,
        )
        pl.add_lines(np.repeat(wall, 2, axis=0)[1:-1], color="#d9dde6", width=4)
        pl.add_lines(np.repeat(wall * [1, -1, 1], 2, axis=0)[1:-1], color="#d9dde6", width=4)
        pl.add_scalar_bar(
            "Mach number",
            mapper=a_top.mapper,
            below_label="",
            position_x=0.06,
            position_y=0.88,
            width=0.3,
            height=0.05,
            title_font_size=int(26 * k),
            label_font_size=int(20 * k),
            n_labels=6,
            fmt="%.1f",
        )
        pl.add_scalar_bar(
            "Temperature (K)",
            mapper=a_bot.mapper,
            position_x=0.06,
            position_y=0.05,
            width=0.3,
            height=0.05,
            title_font_size=int(26 * k),
            label_font_size=int(20 * k),
            n_labels=5,
            fmt="%.0f",
        )
        pl.add_text(
            f"t = {t * 1e3:6.3f} ms",
            position=(int(width * 0.80), int(height * 0.92)),
            font_size=int(24 * k),
            color="white",
        )
        pl.add_text(
            "Raptor 3 sea-level estimate, Pc 350 bar, eps 34.34, 1 atm. FoamStudio + OpenFOAM",
            position=(int(width * 0.46), int(height * 0.03)),
            font_size=int(12 * k),
            color="#9aa9c9",
        )
        pl.view_xy()
        pl.camera.parallel_projection = True
        pl.camera.focal_point = (5.9, 0, 0.0)
        pl.camera.position = (5.9, 0, 30)
        pl.camera.parallel_scale = 3.6
        pl.screenshot(str(png))
        pl.close()
        print(png.name, f"{t:.6f}", flush=True)


# name: (title, cmap, clim, log, label fmt, ambient value -> background colour)
FIELDS = {
    "mach": ("Mach number", "turbo", (0.0, 4.8), False, "%.1f", 0.0),
    "velocity": ("Velocity magnitude (m/s)", "plasma", (0.0, 4000.0), False, "%.0f", 0.0),
    "pressure": ("Static pressure (bar)", "RdYlBu_r", (0.2, 350.0), True, "%.3g", 1.013),
    "temperature": ("Temperature (K)", "inferno", (250.0, 3800.0), False, "%.0f", 288.0),
    "density": ("Density (kg/m^3)", "viridis", (0.03, 40.0), True, "%.2g", 1.2),
}


def field_frames(case: Path, out: Path, width: int = 3840) -> None:
    """One mirrored full-nozzle video per field in FIELDS: out/<field>/frame_NNNNN.png."""
    import matplotlib as mpl
    import pyvista as pv

    m = json.loads((case / "case-meta.json").read_text())
    r = _reader(case)
    times = [t for t in r.time_values if t > 0]
    height, k = int(width * 9 / 16), width / 1920
    contour = np.loadtxt(case / "contour.csv", delimiter=",", skiprows=1)
    wall = np.c_[contour[:, 0], contour[:, 1], np.zeros(len(contour))]
    bg = {}
    for name, (_, cmap, clim, log, _, amb) in FIELDS.items():
        norm = mpl.colors.LogNorm(*clim) if log else mpl.colors.Normalize(*clim)
        bg[name] = mpl.colors.to_hex(mpl.colormaps[cmap](float(norm(amb))))
        (out / name).mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(times):
        todo = [n for n in FIELDS if not (out / n / f"frame_{i:05d}.png").exists()]
        if not todo:
            continue
        r.set_active_time_value(t)
        mesh = r.read()["internalMesh"].cell_data_to_point_data()
        speed = np.linalg.norm(mesh["U"], axis=1)
        mesh["mach"] = speed / np.sqrt(m["gamma"] * m["R"] * mesh["T"])
        mesh["velocity"], mesh["pressure"] = speed, mesh["p"] / 1e5
        mesh["temperature"], mesh["density"] = mesh["T"], mesh["rho"]
        full = mesh.merge(mesh.reflect((0, 1, 0), point=(0, 0, 0)))
        for name in todo:
            title, cmap, clim, log, fmt, _ = FIELDS[name]
            fg = "black" if mpl.colors.rgb_to_hsv(mpl.colors.to_rgb(bg[name]))[2] > 0.6 else "white"
            pl = pv.Plotter(off_screen=True, window_size=(width, height))
            pl.set_background(bg[name])
            pl.add_mesh(
                full, scalars=name, cmap=cmap, clim=clim, log_scale=log,
                lighting=False, show_scalar_bar=False,
            )  # fmt: skip
            for sgn in (1, -1):
                pl.add_lines(np.repeat(wall * [1, sgn, 1], 2, axis=0)[1:-1], color="#d9dde6", width=4)
            pl.add_scalar_bar(
                " ", position_x=0.06, position_y=0.04, width=0.36, height=0.08,
                title_font_size=int(26 * k), label_font_size=int(20 * k), n_labels=6, fmt=fmt,
                color=fg,
            )  # fmt: skip
            pl.add_text(title, position=(int(width * 0.065), int(height * 0.12)),
                        font_size=int(16 * k), color=fg)  # fmt: skip
            pl.add_text(f"t = {t * 1e3:6.3f} ms", position=(int(width * 0.80), int(height * 0.92)),
                        font_size=int(24 * k), color=fg)  # fmt: skip
            pl.add_text("Raptor 3 sea-level estimate, Pc 350 bar, eps 34.34, 1 atm. FoamStudio + OpenFOAM",
                        position=(int(width * 0.46), int(height * 0.03)), font_size=int(12 * k), color=fg)  # fmt: skip
            pl.view_xy()
            pl.camera.parallel_projection = True
            pl.camera.focal_point, pl.camera.position = (5.9, 0, 0.0), (5.9, 0, 30)
            pl.camera.parallel_scale = 3.6
            pl.screenshot(str(out / name / f"frame_{i:05d}.png"))
            pl.close()
        print(i, f"{t:.6f}", flush=True)


if __name__ == "__main__":
    cmd, target = sys.argv[1], Path(sys.argv[2])
    if cmd == "validate":
        print(json.dumps(validate(target), indent=2))
    elif cmd == "raptor":
        print(json.dumps(raptor(target), indent=2, default=float))
    elif cmd == "frames":
        width = int(sys.argv[sys.argv.index("--width") + 1]) if "--width" in sys.argv else 3840
        frames(target, Path(sys.argv[3]), width)
    elif cmd == "fields":
        width = int(sys.argv[sys.argv.index("--width") + 1]) if "--width" in sys.argv else 3840
        field_frames(target, Path(sys.argv[3]), width)
