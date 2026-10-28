() => {
  // Gap-closing tests: mesh conversion, parallel, turboPerf, potentialFoam init, quality gate, convergence stop
  const CH = [['inlet','inlet'],['outlet','outlet'],['walls','wall'],['frontAndBack','empty']];
  const CH3 = [['inlet','inlet'],['outlet','outlet'],['walls','wall'],['frontAndBack','wall']];
  const USER = [['inlet','inlet'],['outlet','outlet'],['circle_1_walls','wall'],['circle_2_walls','wall'],['walls','wall'],['frontAndBackPlanes','empty']];
  const TANK = [['inlet','wall'],['outlet','wall'],['walls','wall'],['atmosphere','opening'],['frontAndBack','empty']];
  const steady = {endTime:5, deltaT:1, writeInterval:5, writeControl:'timeStep'};
  const trans = {endTime:5e-4, deltaT:1e-4, writeInterval:5, writeControl:'timeStep', maxCo:0.5};
  const VB = {vofBoxMin:'(0 0 -1)', vofBoxMax:'(0.5 0.2 1)'};
  const T = [
    ['simpleFoam', 'msh:user2d', USER, {meshDim:'2D', nu:1e-6}, 'conv2D'],
    ['simpleFoam', 'msh:channel3d_mm', CH3, {meshDim:'3D', meshScale:0.001, turbModel:'laminar'}, 'conv3Dmm'],
    ['simpleFoam', 'channel2d', CH, {nProcs:2, decompMethod:'scotch'}, 'par'],
    ['pimpleFoam', 'channel2d', CH, {nProcs:2, decompMethod:'scotch', writeEvery:1}, 'par'],
    ['interFoam', 'tank2d', TANK, Object.assign({nProcs:2, decompMethod:'scotch', writeEvery:1}, VB), 'par'],
    ['chtMultiRegionSimpleFoam', 'chtChannel', CH, {nProcs:2, decompMethod:'scotch'}, 'par'],
    ['simpleFoam', 'channel2d', CH, {motion:'mrf', turboPerf:true, rotPatches:'walls'}, 'turbo'],
    ['pimpleFoam', 'channel2d', CH, {turboPerf:true, rotPatches:'walls'}, 'turbo'],
    ['simpleFoam', 'channel2d', CH, {potentialInit:true}, 'potInit'],
    ['interFoam', 'tank2d', TANK, Object.assign({potentialInit:true}, VB), 'potInit'],
    ['simpleFoam', 'skewed2d', CH, {}, 'skewGate'],
    ['simpleFoam', 'channel2d', CH, {convTol:1e-3, convWindow:20, longRun:true}, 'convStop'],
    ['simpleFoam', 'channel2d', CH, {wallTx:'lowRe', yplusRun:true}, 'yPlus']
  ];
  const VERS = window.__vers || ['2412', '12'];
  const out = {};
  const base = JSON.parse(JSON.stringify(STATE));
  const reset = {motion:'none', turboPerf:false, rotZone:'rotor', planeStress:false, nProcs:1, potentialInit:false, meshDim:'3D', meshScale:1, rotPatches:''};
  for (const v of VERS) for (const [solver, mesh, pats, ov, tag] of T) {
    Object.assign(STATE, JSON.parse(JSON.stringify(base)), reset);
    document.getElementById('ofVersion').value = v;
    document.getElementById('solverSelect').value = solver;
    onSolverChange();
    if (!solverAvailability().ok) continue;
    STATE.patches = pats.map(([n, r]) => makePatch(n, r));
    Object.assign(STATE, ov);
    STATE.control = Object.assign({}, STATE.control, isTransient() ? trans : steady);
    if (ov.longRun || ov.yplusRun) STATE.control = Object.assign(STATE.control, {endTime: ov.longRun ? 3000 : 50, writeInterval: ov.longRun ? 3000 : 50});
    if (ov.writeEvery) STATE.control.writeInterval = ov.writeEvery;
    const name = `${v}_${solver}_${tag}`;
    out[name] = { mesh, ver: v, files: buildCaseFiles(name) };
  }
  return JSON.stringify(out);
}
