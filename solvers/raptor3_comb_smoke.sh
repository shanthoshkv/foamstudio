#!/bin/bash
# Serial N-iteration timing test of the reacting case (default 3). Restores controlDict after.
#   wsl -- bash solvers/raptor3_comb_smoke.sh 5
source /usr/lib/openfoam/openfoam2412/etc/bashrc
cd ~/foamstudio/nozzles/raptor3-comb || exit 1
N=${1:-3}
cp system/controlDict cd.bak
foamDictionary -entry endTime -set "$N" system/controlDict >/dev/null
foamDictionary -entry writeInterval -set "$N" system/controlDict >/dev/null
rm -rf [1-9]*
/usr/bin/time -f "wall %e s" timeout 3000 reactingFoam > log.smoke 2>&1
echo "rc=$? underflows=$(grep -c underflow log.smoke)"
cp cd.bak system/controlDict
grep -E "ExecutionTime" log.smoke | tail -"$N"
grep -B2 -A12 -m1 "FATAL\|stack trace" log.smoke | head -30
