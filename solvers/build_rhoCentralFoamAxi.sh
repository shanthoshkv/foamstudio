#!/bin/bash
# rhoCentralFoam with wedge patches left out of the Courant sum.
# Wedge faces carry no flux, but their large area/volume ratio near the axis made
# the stock solver cut deltaT ~12x on axisymmetric meshes. Physics is unchanged.

source /usr/lib/openfoam/openfoam2412/etc/bashrc || true
set -e
dst="$WM_PROJECT_USER_DIR/applications/rhoCentralFoamAxi"
rm -rf "$dst"; mkdir -p "$(dirname "$dst")"
cp -r "$FOAM_SOLVERS/compressible/rhoCentralFoam" "$dst"
cd "$dst"
rm -rf BCs Allwmake Allwclean
sed -i 's|^EXE = .*|EXE = $(FOAM_USER_APPBIN)/rhoCentralFoamAxi|' Make/files
sed -i "s|-IBCs/lnInclude|-I$FOAM_SOLVERS/compressible/rhoCentralFoam/BCs/lnInclude|" Make/options
python3 - <<'PY'
p = "centralCourantNo.H"
s = open(p).read()
s = s.replace(
    "    scalarField sumAmaxSf(fvc::surfaceSum(amaxSf)().primitiveField());",
    """    surfaceScalarField amaxSfIn(amaxSf);
    forAll(mesh.boundary(), patchi)
    {
        if (isA<wedgeFvPatch>(mesh.boundary()[patchi]))
        {
            amaxSfIn.boundaryFieldRef()[patchi] = 0;
        }
    }
    scalarField sumAmaxSf(fvc::surfaceSum(amaxSfIn)().primitiveField());""")
open(p, "w").write(s)
p = "rhoCentralFoam.C"
s = open(p).read()
s = s.replace('#include "fvCFD.H"', '#include "fvCFD.H"\n#include "wedgeFvPatch.H"', 1)
# Positivity floor (same idea as the limitTemperature fvConstraint, which this solver lacks):
# violent start-up expansions can drive e = rhoE/rho - |U|^2/2 below zero, and sqrt(gamma*R*T)
# then raises SIGFPE. Clipped cells are counted and logged every step.
old = "        e = rhoE/rho - 0.5*magSqr(U);\n        e.correctBoundaryConditions();"
new = """        e = rhoE/rho - 0.5*magSqr(U);
        {
            const scalar Tmin =
                runTime.controlDict().getOrDefault<scalar>("Tmin", 50);
            volScalarField Tfloor(thermo.T());
            Tfloor.primitiveFieldRef() = Tmin;
            const volScalarField eMin(thermo.he(p, Tfloor));
            scalarField& eI = e.primitiveFieldRef();
            label nClip = 0;
            forAll(eI, i)
            {
                if (eI[i] < eMin[i])
                {
                    eI[i] = eMin[i];
                    rhoE[i] = rho[i]*(eI[i] + 0.5*magSqr(U[i]));
                    ++nClip;
                }
            }
            reduce(nClip, sumOp<label>());
            if (nClip)
            {
                Info<< "Tmin floor applied in " << nClip << " cells" << endl;
            }
        }
        e.correctBoundaryConditions();"""
assert old in s
s = s.replace(old, new, 1)
open(p, "w").write(s)
PY
grep -q wedgeFvPatch centralCourantNo.H
wmake > log.wmake 2>&1 || { tail -30 log.wmake; exit 1; }
ls -la "$FOAM_USER_APPBIN/rhoCentralFoamAxi"
