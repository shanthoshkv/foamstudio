// Run the generator embedded in openfoam_case_generator.html under Node (no browser).
// Stubs just enough DOM for the page script to load; generation functions are pure.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function stubElement(id) {
  const el = {
    id, value: undefined, checked: false, innerHTML: '', textContent: '', innerText: '',
    style: {}, dataset: {}, options: [], children: [],
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, removeEventListener() {}, appendChild() {}, setAttribute() {}, getAttribute() { return null; },
    querySelector() { return null; }, querySelectorAll() { return []; }, getContext() { return null; },
    click() {}, focus() {}, scrollIntoView() {}
  };
  return el;
}

function loadGenerator(htmlPath = path.join(__dirname, '..', 'openfoam_case_generator.html')) {
  const html = fs.readFileSync(htmlPath, 'utf8');
  const scripts = [...html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  // default values of <select>/<input> by id, so ofVer() etc. match the page defaults
  const defaults = {};
  for (const m of html.matchAll(/<select[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {
    const sel = m[2].match(/<option value="([^"]*)"[^>]*selected/) || m[2].match(/<option value="([^"]*)"/);
    if (sel) defaults[m[1]] = sel[1];
  }
  for (const m of html.matchAll(/<input[^>]*id="([^"]+)"[^>]*value="([^"]*)"/g)) defaults[m[1]] = m[2];
  const els = {};
  const document = {
    getElementById(id) { if (!els[id]) { els[id] = stubElement(id); els[id].value = defaults[id]; } return els[id]; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener() {}, createElement: () => stubElement(''), body: stubElement('body')
  };
  const sandbox = {
    document, console, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0,
    alert() {}, confirm: () => true, navigator: {}, location: { href: '' }, localStorage: { getItem: () => null, setItem() {} },
    URL: { createObjectURL: () => '', revokeObjectURL() {} }, Blob: function () {}, File: function () {},
    Chart: function () { return { destroy() {}, update() {} }; }, JSZip: function () { return { file() {}, generateAsync: async () => null }; },
    Math, JSON, Date, Object, Array, Number, String, RegExp, Set, Map, Promise, parseFloat, parseInt, isNaN, isFinite
  };
  sandbox.window = sandbox; sandbox.globalThis = sandbox; sandbox.self = sandbox;
  vm.createContext(sandbox);
  // top-level const/let/function declarations become globals of the context when run as one script
  vm.runInContext(scripts.join('\n;\n'), sandbox, { filename: 'openfoam_case_generator.html' });
  if (typeof sandbox.window.onload === 'function') { try { sandbox.window.onload(); } catch (e) { /* UI-only */ } }
  // expose lexical (const/let) bindings
  const g = vm.runInContext('({ STATE, SOLVERS, buildCaseFiles, makePatch, onSolverChange, solverAvailability, isTransient, solverFam, caseSpec, specHash, GEN_VERSION, validateSpec: typeof validateSpec === "function" ? validateSpec : null })', sandbox);
  g.ctx = sandbox;
  g.setVersion = v => { document.getElementById('ofVersion').value = String(v); };
  g.setSolver = s => { document.getElementById('solverSelect').value = s; sandbox.onSolverChange(); };
  g.setCaseName = n => { document.getElementById('caseNameInput').value = n; };
  g.run = code => vm.runInContext(code, sandbox);
  return g;
}

module.exports = { loadGenerator };

function argValue(args, flag) {
  const index = args.indexOf(flag);
  if (index < 0) return null;
  const value = args[index + 1];
  if (!value || value.startsWith('--')) return null;
  return value;
}

if (require.main === module) {
  const args = process.argv.slice(2);
  try {
    if (args.includes('--apply-spec')) {
      const specPath = argValue(args, '--apply-spec');
      if (!specPath) {
        console.error('--apply-spec needs a path to case.json');
        process.exit(2);
      }
      const g = loadGenerator();
      const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
      const name = argValue(args, '--name') || spec.caseName || 'case';
      g.ctx.applySpec(spec);
      process.stdout.write(JSON.stringify(g.buildCaseFiles(name)));
    } else if (args.includes('--apply-many')) {
      const jobsPath = argValue(args, '--apply-many');
      if (!jobsPath) {
        console.error('--apply-many needs a path to a JSON job list');
        process.exit(2);
      }
      const jobs = JSON.parse(fs.readFileSync(jobsPath, 'utf8'));
      const out = [];
      for (const job of jobs) {
        try {
          const g = loadGenerator();
          g.ctx.applySpec(JSON.parse(job.specText));
          out.push({ name: job.name, files: g.buildCaseFiles(job.name) });
        } catch (err) {
          console.error(String(job && job.name) + ': ' + (err && err.stack ? err.stack : err));
          process.exit(1);
        }
      }
      process.stdout.write(JSON.stringify(out));
    } else if (args.includes('--generate')) {
      const fn = argValue(args, '--generate');
      if (!fn) {
        console.error('--generate needs a file name, for example gen_fn.js');
        process.exit(2);
      }
      const versArg = argValue(args, '--vers');
      const vers = versArg ? versArg.split(',') : ['2412'];
      const { generate } = require('./gen');
      process.stdout.write(JSON.stringify(generate(fn, vers)));
    } else {
      const g = loadGenerator();
      g.setVersion(2412); g.setSolver('simpleFoam');
      g.STATE.patches = [['inlet', 'inlet'], ['outlet', 'outlet'], ['walls', 'wall'], ['frontAndBack', 'empty']].map(([n, r]) => g.ctx.makePatch(n, r));
      const F = g.buildCaseFiles('smoke');
      console.log(Object.keys(F).length, 'files; generator', g.GEN_VERSION);
    }
  } catch (err) {
    console.error(err && err.stack ? err.stack : err);
    process.exit(1);
  }
}
