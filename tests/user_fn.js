() => {
  const PATS = [['inlet','inlet'],['outlet','outlet'],['circle_1_walls','wall'],['circle_2_walls','wall'],['walls','wall'],['frontAndBackPlanes','empty']];
  const out = {};
  const base = JSON.parse(JSON.stringify(STATE));
  for (const v of ['2406','2412','12','13','14']) for (const [solver, extra, tag] of [
      ['simpleFoam', {}, ''], ['simpleFoam', {wallTx:'lowRe'}, '_lowRe'], ['simpleFoam', {turbModel:'kEpsilon'}, '_kEps'],
      ['simpleFoam', {turbModel:'SpalartAllmaras'}, '_SA'], ['pimpleFoam', {}, ''], ['rhoSimpleFoam', {}, '']]) {
    Object.assign(STATE, JSON.parse(JSON.stringify(base)));
    document.getElementById('ofVersion').value = v;
    document.getElementById('solverSelect').value = solver;
    onSolverChange();
    STATE.patches = PATS.map(([n,r]) => makePatch(n,r));
    Object.assign(STATE, extra, { nu: 1e-6, schemes: 'accurate' });
    STATE.control = Object.assign({}, STATE.control, isTransient() ? {endTime:2e-3, deltaT:1e-3, writeInterval:2, writeControl:'timeStep', maxCo:0.5} : {endTime:20, deltaT:1, writeInterval:20, writeControl:'timeStep'});
    const name = `${v}_user_${solver}${tag}`;
    out[name] = { mesh: 'userMesh', ver: v, files: buildCaseFiles(name) };
  }
  return JSON.stringify(out);
}
