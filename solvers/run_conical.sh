source /usr/lib/openfoam/openfoam2412/etc/bashrc || true
cd /home/shanthoshkv/foamstudio/nozzles
until grep -q "iso9300-R4-fine finished" validation.status; do sleep 60; done
cd conical15-eps4-medium && rm -f 0/C 0/Cx 0/Cy 0/Cz
sed -i "s/^numberOfSubdomains .*/numberOfSubdomains 3;/" system/decomposeParDict
decomposePar -force > log.decompose 2>&1
mpirun --use-hwthread-cpus --bind-to none -np 3 rhoCentralFoamAxi -parallel > log.solver 2>&1
echo "$(date +%T) conical15-eps4-medium finished rc=$?" >> ../validation.status
reconstructPar -newTimes > log.reconstruct 2>&1
