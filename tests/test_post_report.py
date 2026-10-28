"""Fields, turbo numbers, images, GCI, nozzle checks, and validation samples."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from foamstudio.core.logparse import parse_monitor_table, parse_solver_log
from foamstudio.core.post.fields import parse_internal_field, read_field
from foamstudio.core.post.filters import clip_triangles, iso_segments, slice_segments, streamline
from foamstudio.core.post.image import mean_abs_diff, write_png
from foamstudio.core.post.paraview import (
    ParaViewFailure,
    launch_argv,
    pvpython_script,
    state_opens,
    write_foam,
    write_state,
)
from foamstudio.core.post.report import (
    ReportFailure,
    ReportInputs,
    SeriesPoint,
    compare_scalar,
    compare_series,
    gci_fine,
    inputs_for_case,
    load_reference,
    mach_from_area,
    pressure_ratio,
    render_html,
    write_html,
)
from foamstudio.core.post.turbo import performance_from_rows

_ROOT = Path(__file__).parents[1]
_LOG = """Time = 1
Solving for p, Initial residual = 0.01, Final residual = 1e-6
Courant Number mean: 0.2 max: 0.4
Time = 2
Solving for p, Initial residual = 1e-4, Final residual = 1e-8
"""


def test_solver_log_and_monitor() -> None:
    snapshot = parse_solver_log(_LOG)
    assert snapshot.residuals[-1].initial == pytest.approx(1e-4)
    assert snapshot.courant[0].maximum == pytest.approx(0.4)
    table = parse_monitor_table("# time force\n0.1 1.5\n(skip)\n", name="force")
    assert table[0].values == (1.5,)


def test_fields_ascii_and_count(tmp_path: Path) -> None:
    scalar = tmp_path / "p"
    scalar.write_text("internalField uniform 1.5;\n", encoding="utf-8")
    field = read_field(scalar)
    assert field.values == (1.5,)
    assert field.source in {"ascii", "foamlib"}
    vector = parse_internal_field("internalField uniform (1 2 3);")
    assert vector.kind == "vector"
    assert vector.values == (1.0, 2.0, 3.0)
    listed = parse_internal_field("internalField nonuniform List<scalar> 2 (1 2);")
    assert listed.values == (1.0, 2.0)
    with pytest.raises(ValueError, match="declares 2"):
        parse_internal_field("internalField nonuniform List<scalar> 2 (1);")


def test_turbo_esi_and_foundation() -> None:
    esi = performance_from_rows(
        moment=[0.0, 0.0, 0.0, 2.0],
        forces=None,
        inlet=[0.0, 1.0, 0.0, 0.0, 1.0],
        outlet=[0.0, 2.0, 0.0, 0.0, 1.0],
        flow_row=[0.0, 0.5],
        rho=1.0,
        omega=10.0,
        axis=(0.0, 0.0, 1.0),
        kinematic_p=False,
    )
    assert esi.flavour == "esi"
    assert esi.torque == pytest.approx(2.0)
    assert esi.power == pytest.approx(20.0)
    assert esi.efficiency is not None
    foundation = performance_from_rows(
        moment=None,
        forces=[0.0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0],
        inlet=None,
        outlet=None,
        flow_row=None,
        rho=1.0,
        omega=2.0,
    )
    assert foundation.flavour == "foundation"
    assert foundation.torque == pytest.approx(2.0)


def test_paraview_state_and_image(tmp_path: Path) -> None:
    case = tmp_path / "cavity"
    case.mkdir()
    foam = write_foam(case)
    state = write_state(foam, case / "cavity.pvsm")
    assert state_opens(state).endswith(".foam")
    script = pvpython_script(foam, case / "shot.png")
    assert "OpenFOAMReader" in script
    assert launch_argv("paraview", state)[0] == "paraview"
    with pytest.raises(ParaViewFailure, match="FOAMSTUDIO_PARAVIEW"):
        launch_argv("  ", state)
    left = tmp_path / "a.png"
    right = tmp_path / "b.png"
    red = [[(255, 0, 0), (255, 0, 0)]]
    shifted = [[(250, 0, 0), (255, 0, 0)]]
    write_png(left, red)
    write_png(right, shifted)
    assert mean_abs_diff(left, left) == 0
    assert mean_abs_diff(left, right) < 2


def test_slice_clip_iso_and_streamline() -> None:
    above = ((0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0))
    across = ((0.0, 0.0, -1.0), (1.0, 0.0, -1.0), (0.5, 0.0, 1.0))
    kept = clip_triangles([above, across], (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert above in kept
    assert across not in kept
    segments = slice_segments([across], (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert len(segments) == 1
    iso = iso_segments([(across, (0.0, 0.0, 1.0))], 0.5)
    assert len(iso) == 1
    path = streamline(
        (0.0, 0.0, 0.0),
        lambda _point: (1.0, 0.0, 0.0),
        steps=2,
        dt=1.0,
    )
    assert path[-1] == pytest.approx((2.0, 0.0, 0.0))


def test_gci_and_nozzle() -> None:
    assert gci_fine(1.0, 1.1, 1.3, 2) == pytest.approx(0.125)
    with pytest.raises(ReportFailure, match="greater than 1"):
        gci_fine(1.0, 1.1, 1.3, 1)
    assert pressure_ratio(1.0) == pytest.approx(0.5282817877171742)
    assert mach_from_area(2.0, supersonic=True) == pytest.approx(2.1971981216521863, rel=1e-5)
    assert mach_from_area(1.0, supersonic=False) == pytest.approx(1.0)
    with pytest.raises(ReportFailure, match="below 1"):
        mach_from_area(0.5, supersonic=False)


def test_validation_samples_match_reference(tmp_path: Path) -> None:
    cavity = load_reference(_ROOT / "samples" / "cavity" / "reference.json")
    points = [
        SeriesPoint(float(item["x"]), float(item["y"]))  # type: ignore[index]
        for item in cavity["series"]  # type: ignore[union-attr]
    ]
    shifted = tuple(SeriesPoint(point.x, point.y + 0.01) for point in points)
    assert compare_series(tuple(points), shifted, float(cavity["tolerance"])) == []  # type: ignore[arg-type]
    broken = tuple(SeriesPoint(point.x, point.y + 1.0) for point in points)
    assert compare_series(tuple(points), broken, float(cavity["tolerance"]))  # type: ignore[arg-type]

    step = load_reference(_ROOT / "samples" / "backward-facing-step" / "reference.json")
    assert compare_scalar("xr/h", 6.4, float(step["value"]), float(step["tolerance"])) == []  # type: ignore[arg-type]
    assert compare_scalar("xr/h", 8.0, float(step["value"]), float(step["tolerance"]))  # type: ignore[arg-type]

    naca = load_reference(_ROOT / "samples" / "naca0012" / "reference.json")
    rows = list(naca["coefficients"])  # type: ignore[arg-type]
    zero = rows[0]
    ten = rows[1]
    assert compare_scalar("Cl", 0.01, float(zero["cl"]), float(zero["cl_tolerance"])) == []
    assert compare_scalar("Cd", 0.008, float(zero["cd"]), float(zero["cd_tolerance"])) == []
    assert compare_scalar("Cl", 1.03, float(ten["cl"]), float(ten["cl_tolerance"])) == []

    nozzle = load_reference(_ROOT / "samples" / "nozzle" / "reference.json")
    mach = mach_from_area(float(nozzle["area_ratio"]), supersonic=True)  # type: ignore[arg-type]
    assert (
        compare_scalar(
            "Mach",
            mach,
            float(nozzle["mach_supersonic"]),  # type: ignore[arg-type]
            float(nozzle["tolerance"]),  # type: ignore[arg-type]
        )
        == []
    )
    assert pressure_ratio(1.0) == pytest.approx(float(nozzle["throat_pressure_ratio"]))  # type: ignore[arg-type]

    for name in ("cavity", "backward-facing-step", "naca0012"):
        report = ReportInputs(
            title=name,
            solver="simpleFoam",
            mesh_summary="reference mesh",
            residual_final=1e-6,
            integrals=(("check", 1.0),),
            yplus=30.0,
            gci=0.125,
            validation=(f"{name} within tolerance",),
        )
        html = render_html(report)
        for heading in ("Setup", "Mesh", "Convergence", "Integrals", "y+", "GCI", "Validation"):
            assert heading in html
        path = write_html(report, tmp_path / name / "report.html")
        assert path.is_file()
        assert json.loads((_ROOT / "samples" / name / "reference.json").read_text(encoding="utf-8"))


def test_inputs_for_case_reads_run_files(tmp_path: Path) -> None:
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    (case / "system" / "controlDict").write_text("application simpleFoam;\n", encoding="utf-8")
    (case / "log.solver").write_text(
        "Time = 1\n"
        "Solving for Ux, Initial residual = 0.2, Final residual = 0.1\n"
        "Time = 2\n"
        "Solving for Ux, Initial residual = 1.5e-6, Final residual = 1e-7\n",
        encoding="utf-8",
    )
    (case / "log.checkMesh").write_text(
        "Mesh non-orthogonality Max: 12\nMax skewness = 0.4\nMesh OK.\n",
        encoding="utf-8",
    )
    (case / "log.yPlus").write_text("patch walls average y+: 31.5\n", encoding="utf-8")
    forces = case / "postProcessing" / "forces" / "0"
    forces.mkdir(parents=True)
    (forces / "forces.dat").write_text("# Time total\n2 1.25 0 0.5\n", encoding="utf-8")
    report = inputs_for_case("cavity", case)
    assert report.solver == "simpleFoam"
    assert report.residual_final == pytest.approx(1.5e-6)
    assert report.yplus == pytest.approx(31.5)
    assert report.integrals == (("force x", 1.25), ("force y", 0.0), ("force z", 0.5))
    assert "Mesh OK: True" in report.mesh_summary
    assert report.problems == ()
    missing = inputs_for_case("empty", tmp_path / "absent")
    assert missing.residual_final is None
    assert "No solver log was found" in missing.problems[0]
