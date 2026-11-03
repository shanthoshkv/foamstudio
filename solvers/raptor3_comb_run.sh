#!/bin/bash
# Parallel LTS run of the reacting case. NP = physical cores (16 on a Ryzen 9 9950X3D).
#   wsl -- bash solvers/raptor3_comb_run.sh 16
source /usr/lib/openfoam/openfoam2412/etc/bashrc
cd ~/foamstudio/nozzles/raptor3-comb || exit 1
NP=${1:-16}
rm -rf processor*
foamDictionary -entry numberOfSubdomains -set "$NP" system/decomposeParDict >/dev/null
decomposePar -force > log.decompose 2>&1 || { echo "decomposePar failed"; exit 1; }
mpirun -np "$NP" reactingFoam -parallel > log.reactingFoam 2>&1
rc=$?
reconstructPar -newTimes > log.reconstruct 2>&1
echo "$(date +%T) reactingFoam rc=$rc"
