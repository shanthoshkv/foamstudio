#!/bin/bash
# Overnight nozzle runs. Raptor on 9 ranks; validation cases one after another on 3 ranks.
source /usr/lib/openfoam/openfoam2412/etc/bashrc || true
ROOT=~/foamstudio/nozzles
run_case() {  # name ranks
  cd "$ROOT/$1" || return 1
  rm -rf processor* [1-9]* 0.[0-9]* postProcessing log.solver log.decompose log.reconstruct
  blockMesh > log.blockMesh 2>&1 || { echo "$1 blockMesh FAILED"; return 1; }
  if [ "$2" -gt 1 ]; then
    sed -i "s/^numberOfSubdomains .*/numberOfSubdomains $2;/" system/decomposeParDict
    decomposePar -force > log.decompose 2>&1
    mpirun --use-hwthread-cpus -np "$2" rhoCentralFoamAxi -parallel > log.solver 2>&1
    rc=$?
    reconstructPar -newTimes > log.reconstruct 2>&1
  else
    rhoCentralFoamAxi > log.solver 2>&1; rc=$?
  fi
  echo "$(date +%T) $1 finished rc=$rc"
}
cd "$ROOT/raptor3-sl" && sed -i 's/^endTime .*/endTime 0.016;/' system/controlDict
run_case raptor3-sl 8 > "$ROOT/raptor.status" 2>&1
