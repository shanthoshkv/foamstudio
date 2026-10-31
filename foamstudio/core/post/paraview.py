"""ParaView stays an external process. FoamStudio writes a .foam file and a state."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from foamstudio.core.runtime.paths import windows_to_wsl


class ParaViewFailure(Exception):
    def __init__(self, message: str, suggestion: str) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"{message}\n\n{suggestion}")


def write_foam(case: Path) -> Path:
    if not case.is_dir():
        raise ParaViewFailure(
            f"{case} is not a case directory.",
            suggestion="Write the case first, then open it in ParaView.",
        )
    target = case / f"{case.name}.foam"
    target.write_text("", encoding="utf-8")
    return target


def write_state(foam_file: Path, state_file: Path) -> Path:
    # NOT loadable: ParaView 2026-10-31 LoadState gives zero sources. Use pvpython_script(state=).
    root = ET.Element("ParaView")
    server = ET.SubElement(root, "ServerManagerState", version="5.11.0")
    proxy = ET.SubElement(server, "Proxy", group="sources", type="OpenFOAMReader", id="1")
    prop = ET.SubElement(proxy, "Property", name="FileName", id="1.FileName")
    ET.SubElement(prop, "Element", index="0", value=str(foam_file))
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    tree.write(state_file, encoding="utf-8", xml_declaration=True)
    return state_file


def state_opens(state_file: Path) -> str:
    """Parse the state. A missing OpenFOAMReader or FileName is an error."""
    try:
        root = ET.parse(state_file).getroot()
    except ET.ParseError as exc:
        raise ParaViewFailure(
            f"{state_file} is not XML: {exc}",
            suggestion="Write the state again from the Results panel.",
        ) from exc
    reader = root.find(".//Proxy[@type='OpenFOAMReader']")
    if reader is None:
        raise ParaViewFailure(
            f"{state_file} has no OpenFOAMReader.",
            suggestion="Write the ParaView state from the case .foam file.",
        )
    element = reader.find("./Property[@name='FileName']/Element")
    if element is None or not element.attrib.get("value"):
        raise ParaViewFailure(
            f"{state_file} does not name a .foam file.",
            suggestion="Write the .foam file next to the case and export the state again.",
        )
    return element.attrib["value"]


def _script_path(path: Path, wsl: bool) -> str:
    text = str(path).replace("\\", "/")
    return windows_to_wsl(text) if wsl and re.match(r"[A-Za-z]:/", text) else text


def pvpython_script(
    foam_file: Path, image: Path, state: Path | None = None, *, wsl: bool = False
) -> str:
    """Run under pvpython. With `state`, ParaView itself writes a loadable .pvsm.

    `wsl=True` rewrites `C:/x` to `/mnt/c/x` for a pvpython inside WSL.
    """
    foam = _script_path(foam_file, wsl)
    picture = _script_path(image, wsl)
    save = f'SaveState("{_script_path(state, wsl)}")\n' if state else ""
    return (
        "from paraview.simple import GetActiveViewOrCreate, OpenFOAMReader, "
        "SaveScreenshot, SaveState, Show\n"
        f'reader = OpenFOAMReader(FileName="{foam}")\n'
        "Show(reader)\n"
        "view = GetActiveViewOrCreate('RenderView')\n"
        f"{save}"
        f'SaveScreenshot("{picture}", view)\n'
    )


def launch_argv(paraview: str, state_file: Path) -> tuple[str, ...]:
    if not paraview.strip():
        raise ParaViewFailure(
            "The paraview executable is not set.",
            suggestion="Install ParaView and set FOAMSTUDIO_PARAVIEW to paraview or paraview.exe.",
        )
    return (paraview, str(state_file))
