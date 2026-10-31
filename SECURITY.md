# Security policy

## Supported versions

Only the latest release on GitHub Releases gets security fixes. FoamStudio is pre-1.0.

## Reporting a vulnerability

Do not open a public issue. Use GitHub private vulnerability reporting:
https://github.com/shanthoshkv/foamstudio/security/advisories/new

Include the FoamStudio version, OS, runtime kind (native, WSL, Docker, SSH), and steps to reproduce.
You get an acknowledgement within 7 days. Fixes are released as a patch version with a GitHub advisory.

## What FoamStudio does on the network

- Nothing by default. The update feed is parsed only if enabled, and no UI enables it yet.
- Crash reports are written locally. Upload happens only with an upload plan **and** `FOAMSTUDIO_CRASH_UPLOAD=1`.
- The SSH runtime calls the system OpenSSH client. FoamStudio never stores passwords or keys.

## Supply chain

Every CI run checks dependency licences (`scripts/license_audit.py`), scans for known CVEs (`pip-audit`),
and on Linux produces a CycloneDX SBOM (`sbom.cdx.json`) as a build artifact. CodeQL scans Python and
JavaScript weekly and on every pull request.
