"""NACA 0012 C-mesh for blockMesh (wrapper over foamstudio.core.mesh.airfoil).

    python nacamesh.py OUT_blockMeshDict [first_cell] [scale]
"""

import sys
from pathlib import Path

from foamstudio.core.mesh.airfoil import c_mesh

first = float(sys.argv[2]) if len(sys.argv) > 2 else 4e-6
scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
Path(sys.argv[1]).write_text(c_mesh("0012", first, scale), encoding="utf-8", newline="\n")
