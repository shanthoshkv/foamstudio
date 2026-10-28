; Inno Setup script for an unsigned FoamStudio folder.
; Build the PyInstaller tree first: pyinstaller packaging/foamstudio.spec
; Authenticode signing is packaging/signing/sign.ps1 and is not run here.

#define MyAppName "FoamStudio"
#define MyAppVersion "0.9.0"
#define MyAppPublisher "Shanthosh K V"
#define MyAppExeName "foamstudio.exe"

[Setup]
AppId={{8F3E2A10-6C4B-4A7E-9D11-0F0A0570D109}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\FoamStudio
DefaultGroupName={#MyAppName}
OutputDir=..\dist-installer
OutputBaseFilename=FoamStudio-{#MyAppVersion}-win64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

[Files]
Source: "..\..\dist\foamstudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FoamStudio"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\FoamStudio"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut"; GroupDescription: "Shortcuts:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch FoamStudio"; Flags: nowait postinstall skipifsilent
