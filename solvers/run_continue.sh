source /usr/lib/openfoam/openfoam2412/etc/bashrc || true
cd ~/foamstudio/nozzles/raptor3-sl
mpirun --use-hwthread-cpus --bind-to none -np 8 rhoCentralFoamAxi -parallel > log.solver 2>&1
echo "$(date +%T) raptor rc=$?" > ../raptor.status
