cd /home/shanthoshkv/foamstudio/nozzles
L=raptor3-sl/log.solver
echo "raptor $(grep "^Time =" $L | tail -1 | cut -d" " -f3) dt=$(grep deltaT $L | tail -1 | cut -d" " -f3) fpe=$(grep -c "exception (8)" $L) procs=$(pgrep -c rhoCentralFoam) | $(tail -n1 validation.status) | $(cat raptor.status 2>/dev/null)"
