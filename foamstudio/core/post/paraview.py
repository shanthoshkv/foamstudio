"""ParaView stays an external process. FoamStudio writes a .foam file and a state."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


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


def pvpython_script(foam_file: Path, image: Path) -> str:
    foam = str(foam_file).replace("\\", "/")
    picture = str(image).replace("\\", "/")
    return (
        "from paraview.simple import GetActiveViewOrCreate, OpenFOAMReader, "
        "SaveScreenshot, Show\n"
        f'reader = OpenFOAMReader(FileName="{foam}")\n'
        "Show(reader)\n"
        "view = GetActiveViewOrCreate('RenderView')\n"
        f'SaveScreenshot("{picture}", view)\n'
    )


def launch_argv(paraview: str, state_file: Path) -> tuple[str, ...]:
    if not paraview.strip():
        raise ParaViewFailure(
            "The paraview executable is not set.",
            suggestion="Install ParaView and set FOAMSTUDIO_PARAVIEW to paraview or paraview.exe.",
        )
    return (paraview, str(state_file))
