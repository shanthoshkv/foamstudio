T=/usr/lib/openfoam/openfoam2412/tutorials
ls $T/incompressible/overPimpleDyMFoam $T/incompressible/adjointOptimisationFoam | head -12
find $T -maxdepth 4 -type d \( -iname '*AMI*' -o -name 'pitzDaily*' -o -iname '*LES*' -o -iname '*pump*' -o -iname '*impeller*' -o -iname '*turbo*' \) | sed "s|$T/||" | head -25
