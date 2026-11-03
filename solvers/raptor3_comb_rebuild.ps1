# Regenerate the Raptor 3 reacting case in WSL from scratch: case files, mesh, patches,
# chemkinToFoam, 1-D initial field.  Run from the repo root in PowerShell:
#   .\solvers\raptor3_comb_rebuild.ps1 [-nx 400] [-nr 160] [-distro Ubuntu-24.04]
param([int]$nx = 400, [int]$nr = 160, [string]$distro = "Ubuntu-24.04", [string]$py = "py -3.12")
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$user = (wsl -d $distro -- whoami).Trim()
$root = "\\wsl.localhost\$distro\home\$user\foamstudio\nozzles"
$case = "$root\raptor3-comb"
wsl -d $distro -- bash -c "mkdir -p ~/foamstudio/nozzles && rm -rf ~/foamstudio/nozzles/raptor3-comb"
Invoke-Expression "$py scripts/raptor_comb.py `"$root`" --nx $nx --nr $nr" 2>$null | Select-Object -First 1
wsl -d $distro -- bash -c "cd ~/foamstudio/nozzles/raptor3-comb && bash Allrun.pre && echo pre-ok"
Invoke-Expression "$py scripts/nozzle_init.py `"$case`""
