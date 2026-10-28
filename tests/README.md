# Generator tests

Two layers:

| Layer | Command | Needs | Time |
|---|---|---|---|
| Quality gate: golden snapshots, invariants, determinism, `case.json` round-trip + validation | `node tests/check.js` | Node only | ~10 s |
| Solver runs: every case runs a few iterations in real OpenFOAM | see below | WSL/Linux + OpenFOAM | ~15 min |

Last full run (generator 2.2.0): **225/225 PASS** on ESI v2406, v2412 and Foundation 12, 13, 14,
**65/65** behaviour checks OK (`last_run_results.txt`, `last_verify_results.txt`).

## Quality gate
- `node tests/check.js`: fails on any change to generated files vs `tests/golden/`, on `undefined`/`NaN`,
  missing provenance, unbalanced braces, `dev(` instead of `dev2(`, non-deterministic output, or a broken spec round-trip.
- Intended change? `node tests/check.js --update`, review the golden diff, bump `GEN_VERSION`, add a CHANGELOG line.

## Solver runs
```bash
node tests/gen.js --vers 2406,2412,12,13,14 gen_fn.js extra_fn.js   # Windows or Linux, writes tests/cases
node tests/gen.js --append user_fn.js                                # optional: your simfoam_testing mesh
# in WSL / Linux:
bash tests/mkmesh.sh                 # test meshes in ~/oftest (ESI v2412 tools)
bash tests/runtests.sh "."           # PASS/FAIL per case (regex filter, e.g. "^(2412|12)_")
bash tests/verify_extra.sh           # checks conversion/parallel/turbo/gates actually worked
```
Version → install: >1000 uses `/usr/lib/openfoam/openfoam<ver>`, else `/opt/openfoam<ver>`.

## Files
- `headless.js` runs the page's inline script in Node with a stub DOM (byte-identical to the browser: verified on 979 files).
- `gen_fn.js` every solver; `extra_fn.js` mesh conversion, parallel, turboPerf, potentialFoam, quality gate, convergence stop, y+;
  `user_fn.js` the real `simfoam_testing` mesh.
- `golden/v<ver>.json` snapshots for ESI 2412/2006 and Foundation 14/12/9.
