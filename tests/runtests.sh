#!/bin/bash
# Run every generated test case against its OpenFOAM version; print PASS/FAIL table
HERE=$(cd "$(dirname "$0")" && pwd)
export SRC="${CASES:-$HERE/cases}"
W=$HOME/oftest/run; mkdir -p $W
ONLY="$1"

run_one() {
  name=$1; W=$HOME/oftest/run
  ver=${name%%_*}; mesh=$(cat "$SRC/$name/.mesh")
  rm -rf $W/$name; cp -r "$SRC/$name" $W/$name; cd $W/$name
  mkdir -p constant
  case $mesh in msh:*) cp $HOME/oftest/msh/${mesh#msh:}.msh . ;; *) cp -r $HOME/oftest/mesh/$mesh/constant/polyMesh constant/ ;; esac
  if [ "$ver" -gt 1000 ]; then source /usr/lib/openfoam/openfoam$ver/etc/bashrc >/dev/null 2>&1; else source /opt/openfoam$ver/etc/bashrc >/dev/null 2>&1; fi
  chmod +x Allrun; timeout 240 ./Allrun > log.Allrun 2>&1
  app=$(foamDictionary -entry application -value system/controlDict 2>/dev/null)
  PAT='FOAM FATAL|sigFpe::sigHandler'
  if grep -Elq "$PAT" log.* 2>/dev/null; then
    f=$(grep -El "$PAT" log.* | head -1)
    msg=$(grep -E -A6 -m1 "$PAT" $f | grep -v "^\s*$" | head -4 | tr '\n' ' ' | cut -c1-300)
    echo "FAIL $name [$f] $msg"
  elif [ -f log.$app ] && grep -Eq "^\s*End" log.$app; then
    echo "PASS $name"
  else
    echo "FAIL $name (no End) $(tail -3 log.$app log.Allrun 2>/dev/null | tr '\n' ' ' | cut -c1-200)"
  fi
}
export -f run_one
ls "$SRC" | grep -E "${ONLY:-.}" | xargs -P 6 -I{} bash -c 'run_one {}' | sort
