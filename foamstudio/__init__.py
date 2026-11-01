"""FoamStudio desktop GUI for OpenFOAM."""

from importlib.metadata import PackageNotFoundError, version

APP_LICENSE = "LicenseRef-FoamStudio-Proprietary"

try:
    __version__ = version("foamstudio")
except PackageNotFoundError:
    __version__ = "0.9.0"

__all__ = ["APP_LICENSE", "__version__"]
