#!/bin/bash
REPO=$(cd "$(dirname "$0")/.." && pwd)
# Build reusable test meshes with ESI v2412 tools into /tmp/ofmesh/<name>/constant/polyMesh
source /usr/lib/openfoam/openfoam2412/etc/bashrc >/dev/null 2>&1
M=$HOME/oftest/mesh; rm -rf $M; mkdir -p $M
T=$FOAM_TUTORIALS

hdr() { cat <<EOF
FoamFile { version 2.0; format ascii; class dictionary; object $1; }
EOF
}
ctrl() { mkdir -p system; cat > system/controlDict <<EOF
FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }
application blockMesh; startFrom startTime; startTime 0; stopAt endTime; endTime 1; deltaT 1; writeControl timeStep; writeInterval 1;
EOF
}

# channel2d: inlet/outlet/walls/frontAndBack, 1 x 0.2 m, with cellZones rotor (cylinder) + porosity (box) + solid/fluid
mk_channel() {
  d=$M/$1; mkdir -p $d; cd $d; ctrl
  cat > system/blockMeshDict <<EOF
$(hdr blockMeshDict)
convertToMeters 1;
vertices ((0 0 0) (1 0 0) (1 0.2 0) (0 0.2 0) (0 0 0.01) (1 0 0.01) (1 0.2 0.01) (0 0.2 0.01));
blocks (hex (0 1 2 3 4 5 6 7) (60 20 1) simpleGrading (1 1 1));
boundary (
  inlet { type patch; faces ((0 4 7 3)); }
  outlet { type patch; faces ((1 2 6 5)); }
  walls { type wall; faces ((0 1 5 4) (3 7 6 2)); }
  frontAndBack { type empty; faces ((0 3 2 1) (4 5 6 7)); }
);
EOF
  blockMesh > log.blockMesh 2>&1
  cat > system/topoSetDict <<EOF
$(hdr topoSetDict)
actions (
  { name rotor; type cellZoneSet; action new; source cylinderToCell; p1 (0.5 0.1 -1); p2 (0.5 0.1 1); radius 0.06; }
  { name porosity; type cellZoneSet; action new; source boxToCell; box (0.4 0 -1) (0.6 0.2 1); }
  { name solidSet; type cellSet; action new; source boxToCell; box (-1 -1 -1) (2 0.06 1); }
  { name solid; type cellZoneSet; action new; source setToCellZone; set solidSet; }
  { name fluidSet; type cellSet; action new; source cellToCell; set solidSet; }
  { name fluidSet; type cellSet; action invert; }
  { name fluid; type cellZoneSet; action new; source setToCellZone; set fluidSet; }
);
EOF
  topoSet > log.topoSet 2>&1
  rm -rf constant/polyMesh/sets
}
mk_channel channel2d
d=$M/chtChannel; mkdir -p $d; cp -r $M/channel2d/system $d/; cd $d; blockMesh > log.blockMesh 2>&1
cat > system/topoSetDict <<EOF
$(hdr topoSetDict)
actions (
  { name solidSet; type cellSet; action new; source boxToCell; box (-1 -1 -1) (2 0.06 1); }
  { name solid; type cellZoneSet; action new; source setToCellZone; set solidSet; }
  { name fluidSet; type cellSet; action new; source cellToCell; set solidSet; }
  { name fluidSet; type cellSet; action invert; }
  { name fluid; type cellZoneSet; action new; source setToCellZone; set fluidSet; }
);
EOF
topoSet > log.topoSet 2>&1; rm -rf constant/polyMesh/sets

# tank2d (VoF): walls + atmosphere (top)
d=$M/tank2d; mkdir -p $d; cd $d; ctrl
cat > system/blockMeshDict <<EOF
$(hdr blockMeshDict)
convertToMeters 1;
vertices ((0 0 0) (0.5 0 0) (0.5 0.5 0) (0 0.5 0) (0 0 0.01) (0.5 0 0.01) (0.5 0.5 0.01) (0 0.5 0.01));
blocks (hex (0 1 2 3 4 5 6 7) (30 30 1) simpleGrading (1 1 1));
boundary (
  inlet { type wall; faces ((0 4 7 3)); }
  outlet { type wall; faces ((1 2 6 5)); }
  walls { type wall; faces ((0 1 5 4)); }
  atmosphere { type patch; faces ((3 7 6 2)); }
  frontAndBack { type empty; faces ((0 3 2 1) (4 5 6 7)); }
);
EOF
blockMesh > log.blockMesh 2>&1

# plateHole (solid)
d=$M/plateHole; cp -r $T/stressAnalysis/solidDisplacementFoam/plateHole $d; cd $d; blockMesh > log.blockMesh 2>&1

# mixerAMI (sliding mesh; patches rotor stator front back AMI1 AMI2; cellZone rotor)
d=$M/mixerAMI; cp -r $T/incompressible/pimpleFoam/laminar/mixerVesselAMI2D/mixerVesselAMI2D $d; cd $d
m4 system/blockMeshDict.m4 > system/blockMeshDict; blockMesh > log.blockMesh 2>&1; topoSet > log.topoSet 2>&1
# turn AMI1/AMI2 into plain patches (what a Fluent interface export looks like)
awk '/^    AMI[12]$/ {inb=1; print; next}
     inb && /^    \{/ {print; print "        type            patch;"; next}
     inb && /nFaces|startFace/ {print; next}
     inb && /^    \}/ {inb=0; print; next}
     inb {next} {print}' constant/polyMesh/boundary > b.tmp && mv b.tmp constant/polyMesh/boundary

# overset simpleRotor (ESI tutorial pre-processing, gives zoneID-ready cellZones)
d=$M/oversetRotor; cp -r $T/incompressible/overPimpleDyMFoam/simpleRotor $d; cd $d
blockMesh > log.blockMesh 2>&1; topoSet > log.topoSet 2>&1; subsetMesh box -patch hole -overwrite > log.subsetMesh 2>&1; topoSet > log.topoSet2 2>&1
cat > system/topoSetDict.zone <<EOF
$(hdr topoSetDict)
actions ( { name movingZone; type cellZoneSet; action new; source setToCellZone; set c1; } );
EOF
topoSet -dict system/topoSetDict.zone > log.topoSet3 2>&1


# skewed2d: uniformly sheared channel (~76 deg non-orthogonality) for the mesh-quality gate
d=$M/skewed2d; mkdir -p $d; cp -r $M/channel2d/system $d/; cd $d
sed -i 's#(1 0.2 0) (0 0.2 0)#(1.8 0.2 0) (0.8 0.2 0)#; s#(1 0.2 0.01) (0 0.2 0.01)#(1.8 0.2 0.01) (0.8 0.2 0.01)#' system/blockMeshDict
blockMesh > log.blockMesh 2>&1
# Fluent meshes for the conversion path: user's 2D msh + 3D msh exported from channel2d (in mm)
mkdir -p $M/../msh
[ -f "$REPO/simplefoam_testing.msh" ] && cp "$REPO/simplefoam_testing.msh" $M/../msh/user2d.msh
cd $M/channel2d; rm -rf fluentInterface; transformPoints -scale 1000 > /dev/null 2>&1; foamMeshToFluent > log.f2f 2>&1
cp fluentInterface/*.msh $M/../msh/channel3d_mm.msh; transformPoints -scale 0.001 > /dev/null 2>&1
ls -la $M/../msh

# user's real mesh (read-only copy of the WSL project, if present)
[ -d ~/openfoamprojects/simfoam_testing/constant/polyMesh ] && mkdir -p $M/userMesh/constant && cp -r ~/openfoamprojects/simfoam_testing/constant/polyMesh $M/userMesh/constant/
for m in $M/*; do echo "$(basename $m): $(grep -c . $m/constant/polyMesh/boundary 2>/dev/null) lines; zones: $(grep -h -A0 '^[a-zA-Z]' $m/constant/polyMesh/cellZones 2>/dev/null | head -0)"; done
for m in $M/*; do echo "== $(basename $m)"; sed -n '/^(/,/^)/p' $m/constant/polyMesh/boundary | grep -E '^\s{4}[A-Za-z]|type' | paste - - | awk '{print $1, $3}' | tr -d ';' | tr '\n' ' '; echo; [ -f $m/constant/polyMesh/cellZones ] && awk '/^\(/{f=1;next} f && /^[A-Za-z]/{printf "zone:%s ",$1}' $m/constant/polyMesh/cellZones; echo; done
