"""Application entry, single-instance guard, and offscreen self-test."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from foamstudio import __version__
from foamstudio.app.crash import install_crash_handler
from foamstudio.app.i18n.loader import install_translators
from foamstudio.app.logging_setup import configure_logging
from foamstudio.app.mainwindow import MainWindow
from foamstudio.app.settings import AppSettings
from foamstudio.app.single_instance import SingleInstance
from foamstudio.app.theme import load_icon

logger = logging.getLogger("foamstudio")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="foamstudio")
    parser.add_argument("--version", action="version", version=f"FoamStudio {__version__}")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Show the window, process events, and exit. Used by CI.",
    )
    parser.add_argument("--theme", choices=("dark", "light"))
    parser.add_argument(
        "--detect-runtimes",
        action="store_true",
        help="Print detected OpenFOAM installations as JSON and exit.",
    )
    parser.add_argument(
        "--write-case",
        metavar="CASE_JSON",
        help="Write dictionaries for this case.json into --project and exit.",
    )
    parser.add_argument(
        "--project",
        metavar="DIR",
        help="Project folder for --write-case and the other batch actions.",
    )
    parser.add_argument(
        "--import-geometry", metavar="FILE", help="Copy a geometry file into --project."
    )
    parser.add_argument(
        "--block-mesh",
        choices=("box", "channel", "wedge"),
        help="Write case/system/blockMeshDict into --project.",
    )
    parser.add_argument("--report", metavar="HTML", help="Write an HTML report.")
    parser.add_argument(
        "--run-case",
        action="store_true",
        help=(
            "Run Allrun steps with --runtime, "
            "or ./Allrun when --command is omitted and --matrix is set."
        ),
    )
    parser.add_argument("--matrix", action="store_true", help="Queue ./Allrun, the 225-case step.")
    parser.add_argument(
        "--command", metavar="CMD", help="Queue this command instead of the Allrun steps."
    )
    parser.add_argument("--runtime", metavar="JSON", help="Runtime JSON from --detect-runtimes.")
    parser.add_argument("--solver", default="simpleFoam")
    parser.add_argument("--np", type=int, default=1)
    parser.add_argument(
        "--mesh-step",
        choices=("blockMesh", "snappyHexMesh", "none"),
        default="blockMesh",
    )
    return parser


def _print_runtimes() -> int:
    from foamstudio.core.runtime import detect

    report = detect()
    print(json.dumps(report.to_dicts(), indent=2))
    for note in report.notes:
        print(note, file=sys.stderr)
    return 0


def build_application(argv: list[str]) -> tuple[QApplication, MainWindow, SingleInstance]:
    cli = _parser().parse_args(argv)
    if cli.self_test:
        os.environ["FOAMSTUDIO_HEADLESS"] = "1"
        os.environ["FOAMSTUDIO_INSTANCE_KEY"] = f"foamstudio-selftest-{os.getpid()}"

    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        app = existing
    else:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication([sys.argv[0]])
    app.setOrganizationName("FoamStudio")
    app.setApplicationName("FoamStudio")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(load_icon())

    configure_logging()
    install_crash_handler(logger)
    install_translators(app)

    key = os.environ.get("FOAMSTUDIO_INSTANCE_KEY", "foamstudio")
    instance = SingleInstance(key)
    window = MainWindow(AppSettings())
    if cli.theme:
        window.set_theme(cli.theme)
    instance.activated.connect(window.raise_and_focus)
    if instance.already_running:
        logger.error("FoamStudio is already running.")
    return app, window, instance


def _write_case_cli(spec_path: Path, project_dir: Path) -> int:
    from foamstudio.core.project import ProjectError, create_project, open_project
    from foamstudio.core.spec import SpecError
    from foamstudio.generator.headless import GeneratorFailure
    from foamstudio.generator.write_case import write_spec_file

    try:
        if (project_dir / "foamstudio.json").is_file():
            project = open_project(project_dir)
        else:
            project = create_project(project_dir, app_version=__version__)
        paths, command = write_spec_file(project, spec_path, app_version=__version__)
    except (OSError, SpecError, ProjectError, GeneratorFailure) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Wrote {len(paths)} files into {project.case_dir}")
    print(command)
    return 0


def _needs_project(parsed: argparse.Namespace) -> bool:
    return bool(
        parsed.write_case
        or parsed.import_geometry
        or parsed.block_mesh
        or parsed.report
        or parsed.run_case
        or parsed.command
        or parsed.matrix
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    parsed = _parser().parse_args(args)
    if parsed.detect_runtimes:
        return _print_runtimes()
    if parsed.project and not _needs_project(parsed):
        print(
            "--project is used with --write-case, --import-geometry, --block-mesh, "
            "--report, or --run-case.",
            file=sys.stderr,
        )
        return 2
    if _needs_project(parsed) and not parsed.project:
        print("That action needs --project DIR.", file=sys.stderr)
        return 2
    if parsed.write_case:
        code = _write_case_cli(Path(parsed.write_case), Path(parsed.project))
        if code != 0:
            return code
    if parsed.import_geometry:
        code = _import_cli(Path(parsed.import_geometry), Path(parsed.project))
        if code != 0:
            return code
    if parsed.block_mesh:
        code = _block_cli(parsed.block_mesh, Path(parsed.project))
        if code != 0:
            return code
    if parsed.report:
        code = _report_cli(Path(parsed.project), Path(parsed.report))
        if code != 0:
            return code
    if parsed.run_case or parsed.command or parsed.matrix:
        if not parsed.runtime:
            print("--run-case needs --runtime JSON.", file=sys.stderr)
            return 2
        return _run_cli(parsed, Path(parsed.project), Path(parsed.runtime))
    if _needs_project(parsed):
        return 0
    try:
        app, window, instance = build_application(args)
    except Exception as exc:
        logging.getLogger("foamstudio").critical(
            "FoamStudio failed to start: %s", exc, exc_info=True
        )
        print(f"FoamStudio failed to start: {exc}", file=sys.stderr)
        return 1
    if instance.already_running:
        return 0
    window.show()
    if "--self-test" in args:
        app.processEvents()
        print("foamstudio: launched")
        window.close()
        instance.close()
        return 0
    window.maybe_prompt_runtime()
    code = app.exec()
    instance.close()
    return int(code)


def _import_cli(geometry: Path, project_dir: Path) -> int:
    from foamstudio.core.geometry import ImportFailure, generator_patches, import_path
    from foamstudio.core.project import ProjectError

    try:
        project = _open_or_create(project_dir)
        surface = import_path(geometry)
        destination = project.geometry_dir / geometry.name
        destination.write_bytes(geometry.read_bytes())
        manifest = project.geometry_dir / "patches.json"
        rows = generator_patches(surface)
        manifest.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    except (OSError, ImportFailure, ProjectError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Imported {geometry.name} with {len(rows)} patches into {destination}")
    return 0


def _block_cli(kind: str, project_dir: Path) -> int:
    from foamstudio.core.mesh import MeshFailure, block_mesh_dict
    from foamstudio.core.project import ProjectError

    try:
        project = _open_or_create(project_dir)
        text = block_mesh_dict(kind)
        target = project.case_dir / "system" / "blockMeshDict"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    except (OSError, MeshFailure, ProjectError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Wrote {target}")
    return 0


def _report_cli(project_dir: Path, destination: Path) -> int:
    from foamstudio.core.logparse import parse_solver_log
    from foamstudio.core.post.report import ReportInputs, write_html
    from foamstudio.core.project import ProjectError

    try:
        project = _open_or_create(project_dir)
        log_path = project.case_dir / "log.solver"
        residual = None
        problems: tuple[str, ...] = ()
        if log_path.is_file():
            snapshot = parse_solver_log(log_path.read_text(encoding="utf-8", errors="replace"))
            if snapshot.residuals:
                residual = snapshot.residuals[-1].initial
        else:
            problems = (
                f"No solver log at {log_path}.",
                "Run the case, then write the report again.",
            )
            print(problems[0], file=sys.stderr)
            print(problems[1], file=sys.stderr)
        report = ReportInputs(
            title=project.root.name,
            solver="recorded in system/controlDict",
            mesh_summary="See case/log.checkMesh when checkMesh has been run.",
            residual_final=residual,
            integrals=(),
            yplus=None,
            gci=None,
            validation=(),
            problems=problems,
        )
        write_html(report, destination)
    except (OSError, ProjectError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Wrote {destination}")
    return 0


def _run_cli(parsed: argparse.Namespace, project_dir: Path, runtime_path: Path) -> int:
    from foamstudio.core.jobs import JobQueue
    from foamstudio.core.project import ProjectError
    from foamstudio.core.runtime import bind
    from foamstudio.core.runtime.model import Installation

    try:
        project = _open_or_create(project_dir)
        installation = Installation.from_dict(json.loads(runtime_path.read_text(encoding="utf-8")))
        queue = JobQueue(bind(installation), project.case_dir)
        if parsed.command:
            queue.add(parsed.command, name="command")
        elif parsed.matrix:
            queue.add_matrix()
        else:
            queue.add_allrun(parsed.solver, parallel=parsed.np, mesh=parsed.mesh_step)
        results = queue.run_blocking(live=True)
    except (OSError, ProjectError, ValueError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 1
    failed = False
    for job in results:
        print(f"{job.status} {job.command}")
        if job.status == "failed":
            failed = True
            print(job.log_tail, file=sys.stderr)
            print(job.suggestion, file=sys.stderr)
    return 1 if failed else 0


def _open_or_create(project_dir: Path):
    from foamstudio.core.project import create_project, open_project

    if (project_dir / "foamstudio.json").is_file():
        return open_project(project_dir)
    return create_project(project_dir, app_version=__version__)


def cli() -> None:
    """Console-script target. setuptools ignores a plain return code."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
