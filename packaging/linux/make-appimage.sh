#!/bin/sh
# AppImage helper. Exits 2 unless FOAMSTUDIO_APPIMAGE=1 and linuxdeploy is on PATH.
# This script was not executed in the Windows development session.
set -eu
if [ "${FOAMSTUDIO_APPIMAGE:-}" != "1" ]; then
  echo "Set FOAMSTUDIO_APPIMAGE=1 to build an AppImage. Nothing was packaged." >&2
  exit 2
fi
if ! command -v linuxdeploy >/dev/null 2>&1; then
  echo "linuxdeploy was not found. Install it, then rerun this script." >&2
  exit 2
fi
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
linuxdeploy --appdir "$root/dist/AppDir" --executable "$root/dist/foamstudio/foamstudio" --output appimage
echo "AppImage build requested. Confirm the file before publishing."
