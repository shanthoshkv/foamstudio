"""Read vertices and hex blocks straight from blockMeshDict text, so edits preview instantly.

ponytail: plain literals only; $macros, #calc and #codeStream raise ValueError (run blockMesh then).
"""

from __future__ import annotations

import re

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


def _section(text: str, key: str) -> str:
    match = re.search(rf"\b{key}\b\s*\(", text)
    if match is None:
        raise ValueError(f"No {key} list in blockMeshDict")
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return text[match.end() : i - 1]


def parse_blockmesh(text: str) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]:
    body = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))
    if re.search(r"\$\w|#calc|#codeStream|#eval", body):
        raise ValueError("Uses macros or #calc; run blockMesh to see this mesh")
    scale = re.search(rf"\b(?:convertToMeters|scale)\s+({_NUM})\s*;", body)
    factor = float(scale.group(1)) if scale else 1.0
    points = [
        (float(x) * factor, float(y) * factor, float(z) * factor)
        for x, y, z in re.findall(
            rf"\(\s*({_NUM})\s+({_NUM})\s+({_NUM})\s*\)", _section(body, "vertices")
        )
    ]
    hexes = [
        tuple(int(v) for v in group.split())
        for group in re.findall(r"\bhex\s*\(([\d\s]+)\)", _section(body, "blocks"))
    ]
    bad = [h for h in hexes if len(h) != 8 or max(h) >= len(points)]
    if not points or not hexes or bad:
        raise ValueError(f"{len(points)} vertices, {len(hexes)} blocks; bad blocks {bad[:3]}")
    return points, hexes
