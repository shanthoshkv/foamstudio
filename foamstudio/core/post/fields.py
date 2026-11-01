"""Read OpenFOAM ASCII fields. Solver dictionaries are written only by the generator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_UNIFORM_SCALAR = re.compile(r"internalField\s+uniform\s+([+-]?[0-9.eE+-]+)\s*;")
_UNIFORM_VECTOR = re.compile(
    r"internalField\s+uniform\s+\(\s*([+-]?[0-9.eE+-]+)\s+"
    r"([+-]?[0-9.eE+-]+)\s+([+-]?[0-9.eE+-]+)\s*\)\s*;"
)
_NONUNIFORM = re.compile(
    r"internalField\s+nonuniform\s+List<(\w+)>\s+(\d+)\s*\((.*?)\)\s*;",
    re.DOTALL,
)
_NUMBER = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class InternalField:
    kind: str
    values: tuple[float, ...]
    source: str


def parse_internal_field(text: str, *, source: str = "ascii") -> InternalField:
    vector = _UNIFORM_VECTOR.search(text)
    if vector is not None:
        values = tuple(float(vector.group(index)) for index in (1, 2, 3))
        return InternalField("vector", values, source)
    scalar = _UNIFORM_SCALAR.search(text)
    if scalar is not None:
        return InternalField("scalar", (float(scalar.group(1)),), source)
    listed = _NONUNIFORM.search(text)
    if listed is not None:
        kind = listed.group(1)
        count = int(listed.group(2))
        numbers = tuple(float(item) for item in _NUMBER.findall(listed.group(3)))
        if len(numbers) != count and kind == "scalar":
            raise ValueError(
                f"internalField declares {count} values but {len(numbers)} were read.\n\n"
                "Rewrite the field as ASCII (foamFormatConvert) and read it again."
            )
        return InternalField(kind, numbers, source)
    raise ValueError(
        "No internalField uniform or nonuniform List entry was found.\n\n"
        "Point this reader at an ASCII 0/ or time-directory field."
    )


def read_field(path: Path) -> InternalField:
    return parse_internal_field(path.read_text(encoding="utf-8", errors="replace"), source="ascii")
