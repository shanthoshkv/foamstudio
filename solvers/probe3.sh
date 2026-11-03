T=/usr/lib/openfoam/openfoam2412/tutorials
ls $T/incompressible/pimpleFoam/laminar/mixerVesselAMI2D; echo ---; ls $T/incompressible/adjointOptimisationFoam/shapeOptimisation; ls $T/incompressible/adjointOptimisationFoam/shapeOptimisation/* | head -20; echo ---
cd /home/shanthoshkv/foamstudio/physcheck/mrf/case && ls; cat Allrun | head -20; tail -5 log.run log.bm log.ts 2>/dev/null
