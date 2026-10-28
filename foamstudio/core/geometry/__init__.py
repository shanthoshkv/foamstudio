"""Geometry import. Patch roles are pushed into the case generator."""

from foamstudio.core.geometry.model import (
    ImportFailure,
    Patch,
    Surface,
    Triangle,
    generator_patches,
    guess_role,
    import_path,
)

__all__ = [
    "ImportFailure",
    "Patch",
    "Surface",
    "Triangle",
    "generator_patches",
    "guess_role",
    "import_path",
]
