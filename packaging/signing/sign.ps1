# Authenticode sign. Refuses to run when the certificate is not configured.
# No signing secret is stored in this repository.
$ErrorActionPreference = "Stop"
if (-not $env:FOAMSTUDIO_SIGN_PFX) {
    Write-Error "FOAMSTUDIO_SIGN_PFX is not set. Refusing to sign. An unsigned installer can still be built with packaging/windows/foamstudio.iss."
    exit 2
}
if (-not $env:FOAMSTUDIO_SIGN_PASSWORD) {
    Write-Error "FOAMSTUDIO_SIGN_PASSWORD is not set. Refusing to sign."
    exit 2
}
$target = $args[0]
if (-not $target) {
    Write-Error "Pass the file to sign, for example dist\installer\FoamStudio-0.9.0-win64.exe."
    exit 2
}
$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $signtool) {
    Write-Error "signtool.exe was not found. Install the Windows SDK signing tools."
    exit 2
}
& $signtool.Source sign /fd SHA256 /f $env:FOAMSTUDIO_SIGN_PFX /p $env:FOAMSTUDIO_SIGN_PASSWORD $target
if ($LASTEXITCODE -ne 0) {
    Write-Error "signtool failed with exit $LASTEXITCODE."
    exit $LASTEXITCODE
}
