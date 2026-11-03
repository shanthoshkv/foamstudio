T=/usr/lib/openfoam/openfoam2412/tutorials
sed -n 5,30p $T/incompressible/pimpleFoam/laminar/mixerVesselAMI2D/mixerVesselAMI2D/Allrun; ls $T/incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/laminar; grep -n cellZone $T/incompressible/simpleFoam/mixerVessel2D/constant/MRFProperties
