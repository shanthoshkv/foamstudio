# CLI

`foamstudio` has no required subcommand. `--self-test` prints `foamstudio: launched` and exits.

| Flag | Effect |
| --- | --- |
| `--version` | Print the version |
| `--self-test` | Show the window offscreen and exit |
| `--detect-runtimes` | JSON installations on stdout, notes on stderr |
| `--project DIR` | Project folder. Required by the actions below |
| `--write-case CASE_JSON` | Run the HTML generator into the project |
| `--import-geometry FILE` | Copy the file and write `geometry/patches.json` |
| `--block-mesh box\|channel\|wedge` | Write `case/system/blockMeshDict` |
| `--report HTML` | Write an HTML report. A missing log is printed and still returns 0 |
| `--run-case` | Run Allrun steps. Requires `--runtime JSON` |
| `--matrix` | Queue `./Allrun` instead of the built-in steps |
| `--command CMD` | Queue this command instead |
| `--solver NAME` | Default `simpleFoam` |
| `--np N` | Process count. Default 1 |
| `--mesh-step blockMesh\|snappyHexMesh\|none` | Default `blockMesh` |
| `--theme dark\|light` | Theme for the window |
| `--runtime JSON` | One installation object from `--detect-runtimes` |

`--detect-runtimes` runs before any GUI or case write. `--project` alone exits 2. An action without `--project` exits 2.

Batch actions run in order and stop at the first failure. When the command line is only batch actions, the window stays closed.

`--run-case` uses the live runner (`MSYS_NO_PATHCONV=1`). Unit tests of the queue use the probe and do not spawn that process.
