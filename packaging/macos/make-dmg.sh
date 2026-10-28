#!/bin/sh
# Unsigned dmg layout. Notarisation is not performed.
# Run on macOS after: FOAMSTUDIO_PYINSTALLER=1 pyinstaller packaging/foamstudio.spec
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
dist="$root/dist/foamstudio"
out="$root/dist/FoamStudio-0.9.0.dmg"
if [ "$(uname -s)" != "Darwin" ]; then
  echo "make-dmg.sh needs macOS hdiutil. This host is $(uname -s)." >&2
  exit 2
fi
if [ ! -d "$dist" ]; then
  echo "Missing $dist. Build the PyInstaller folder first." >&2
  exit 2
fi
rm -f "$out"
hdiutil create -volname FoamStudio -srcfolder "$dist" -ov -format UDZO "$out"
echo "Wrote $out"
echo "Notarisation was not run. Sign the app before sending it to a fresh Mac."
