() => {
  const CH = [['inlet','inlet'],['outlet','outlet'],['walls','wall'],['frontAndBack','empty']];
  const TANK = [['inlet','wall'],['outlet','wall'],['walls','wall'],['atmosphere','opening'],['frontAndBack','empty']];
  const PLATE = [['left','symmetry'],['right','wall'],['down','symmetry'],['up','wall'],['hole','wall'],['frontAndBack','empty']];
  const AMI = [['rotor','wall'],['stator','wall'],['AMI1','ami'],['AMI2','ami'],['front','empty'],['back','empty']];
  const OVS = [['overset2','overset'],['walls','wall'],['hole','wall'],['frontAndBack','empty']];
  const steady = {endTime:5, deltaT:1, writeInterval:5, writeControl:'timeStep'};
  const trans = {endTime:5e-4, deltaT:1e-4, writeInterval:5, writeControl:'timeStep', maxCo:0.5};
  const VB = {vofBoxMin:'(0 0 -1)', vofBoxMax:'(0.5 0.2 1)'};
  const T = [
    ['simpleFoam','channel2d',CH,{}], ['pimpleFoam','channel2d',CH,{}], ['pisoFoam','channel2d',CH,{}], ['icoFoam','channel2d',CH,{}],
    ['porousSimpleFoam','channel2d',CH,{}], ['SRFSimpleFoam','channel2d',CH,{}], ['SRFPimpleFoam','channel2d',CH,{}],
    ['potentialFoam','channel2d',CH,{}], ['scalarTransportFoam','channel2d',CH,{}],
    ['rhoSimpleFoam','channel2d',CH,{}], ['rhoPimpleFoam','channel2d',CH,{}], ['sonicFoam','channel2d',CH,{}], ['rhoCentralFoam','channel2d',CH,{}],
    ['buoyantSimpleFoam','channel2d',CH,{}], ['buoyantPimpleFoam','channel2d',CH,{}],
    ['reactingFoam','channel2d',CH,{}], ['rhoReactingFoam','channel2d',CH,{}], ['XiFoam','channel2d',CH,{}],
    ['simpleFoam','channel2d',CH,{motion:'mrf', turboPerf:true}, 'MRF'],
    ['chtMultiRegionSimpleFoam','chtChannel',CH,{}], ['chtMultiRegionFoam','chtChannel',CH,{}],
    ['interFoam','tank2d',TANK,VB], ['compressibleInterFoam','tank2d',TANK,VB], ['interPhaseChangeFoam','tank2d',TANK,VB],
    ['solidDisplacementFoam','plateHole',PLATE,{planeStress:true}],
    ['pimpleFoam','mixerAMI',AMI,{motion:'ami'}, 'AMI'],
    ['overPimpleDyMFoam','oversetRotor',OVS,{rotZone:'movingZone'}]
  ];
  const VERS = window.__vers || ['2412','12'];
  const out = {};
  const base = JSON.parse(JSON.stringify(STATE));
  const reset = {motion:'none', turboPerf:false, rotZone:'rotor', planeStress:false};
  for (const v of VERS) {
    for (const [solver, mesh, pats, ov, tag] of T) {
      Object.assign(STATE, JSON.parse(JSON.stringify(base)), reset);
      document.getElementById('ofVersion').value = v;
      document.getElementById('solverSelect').value = solver;
      onSolverChange();
      if (!solverAvailability().ok) continue;
      STATE.patches = pats.map(([n,r]) => makePatch(n,r));
      Object.assign(STATE, ov);
      STATE.control = Object.assign({}, STATE.control, isTransient() ? trans : steady);
      if (solver === 'rhoCentralFoam' || solver === 'sonicFoam') { STATE.control.deltaT = 1e-6; STATE.control.endTime = 5e-6; }
      if (solverFam() === 'solid') { STATE.control.deltaT = 1; STATE.control.endTime = 5; }
      const name = `${v}_${solver}${tag ? '_' + tag : ''}`;
      out[name] = { mesh, ver: v, files: buildCaseFiles(name) };
    }
  }
  return JSON.stringify(out);
}
