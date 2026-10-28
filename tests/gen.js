// Headless case generation (replaces the browser step).
// usage: node gen.js [--vers 2412,12] [--append] gen_fn.js [user_fn.js extra_fn.js ...]
const fs = require('fs');
const path = require('path');
const { loadGenerator } = require('./headless');

const args = process.argv.slice(2);
const opt = { vers: null, append: false, out: path.join(__dirname, 'cases'), fns: [] };
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--vers') opt.vers = args[++i].split(',');
  else if (args[i] === '--append') opt.append = true;
  else if (args[i] === '--out') opt.out = args[++i];
  else opt.fns.push(args[i]);
}
if (!opt.fns.length) opt.fns = ['gen_fn.js'];

function generate(fnFile, vers) {
  const g = loadGenerator(); // fresh page state per generator file
  const src = fs.readFileSync(path.join(__dirname, fnFile), 'utf8');
  g.ctx.__vers = vers || undefined;
  return JSON.parse(g.run(`(${src.trim().replace(/;\s*$/, '')})()`));
}

function writeCases(cases, out) {
  for (const [name, c] of Object.entries(cases)) {
    const dir = path.join(out, name);
    fs.rmSync(dir, { recursive: true, force: true });
    for (const [p, txt] of Object.entries(c.files)) {
      const f = path.join(out, ...p.split('/'));
      fs.mkdirSync(path.dirname(f), { recursive: true });
      fs.writeFileSync(f, txt);
    }
    fs.writeFileSync(path.join(dir, '.mesh'), c.mesh);
  }
}

module.exports = { generate };

if (require.main === module) {
  if (!opt.append) fs.rmSync(opt.out, { recursive: true, force: true });
  let n = 0;
  for (const f of opt.fns) { const c = generate(f, opt.vers); writeCases(c, opt.out); n += Object.keys(c).length; }
  console.log(`${n} cases -> ${opt.out}`);
}
