#!/bin/bash
# Behavioural checks for the gap tests (beyond "solver reached End")
cd ~/oftest/run
ok() { echo "OK   $1: $2"; }; bad() { echo "BAD  $1: $2"; }
for c in *_conv2D *_conv3Dmm; do
  [ -d "$c" ] || continue
  conv=$(ls $c/log.fluent*MeshToFoam 2>/dev/null | head -1)
  [ -n "$conv" ] && grep -q "^End" $conv && ok $c "converted by $(basename $conv | cut -d. -f2)" || bad $c "no successful conversion log"
  case $c in *mm) [ -f $c/log.transformPoints ] && ok $c "transformPoints ran" || bad $c "no transformPoints";
      bb=$(grep -m1 "Overall domain bounding box" $c/log.checkMesh); echo "     $bb";; esac
done
for c in *_par; do
  [ -d "$c" ] || continue
  n=$(ls -d $c/processor* 2>/dev/null | wc -l); r=$(ls $c/log.reconstructPar 2>/dev/null)
  [ "$n" -ge 2 ] && [ -n "$r" ] && grep -q "End" $r && ok $c "$n processors, reconstructed" || bad $c "processors=$n reconstruct=$r"
done
for c in *_turbo; do
  [ -d "$c" ] || continue
  grep -q "Torque" $c/log.turboPerf 2>/dev/null && ok $c "$(grep -h 'Torque\|Total-pressure\|Efficiency' $c/log.turboPerf | tr -s ' ' | tr '\n' '|')" || bad $c "$(tail -2 $c/log.turboPerf 2>/dev/null | tr '\n' ' ')"
done
for c in *_potInit; do
  [ -d "$c" ] || continue
  grep -q "^End" $c/log.potentialFoam 2>/dev/null && ok $c "potentialFoam ran" || bad $c "potentialFoam missing/failed"
done
for c in *_skewGate; do
  [ -d "$c" ] || continue
  m=$(grep "non-orthogonality" $c/log.Allrun); [ -n "$m" ] && ok $c "$m" || bad $c "gate did not adjust ($(grep -m1 'non-orthogonality Max' $c/log.checkMesh))"
done
for c in *_convStop; do
  [ -d "$c" ] || continue
  app=$(ls $c/log.simpleFoam $c/log.foamRun 2>/dev/null | head -1)
  last=$(grep "^Time = " $app | tail -1)
  echo "     $c last step: $last ; $(grep -i -m1 'satisfied\|converged in\|runTimeControl' $app)"
done
for c in *_yPlus; do
  [ -d "$c" ] || continue
  [ -s $c/log.yPlusCheck ] && ok $c "$(cat $c/log.yPlusCheck | tr -s ' ' | tr '\n' '|')" || bad $c "no y+ report ($(ls $c/postProcessing 2>/dev/null | tr '\n' ' '))"
done
