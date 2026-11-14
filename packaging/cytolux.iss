; Inno Setup script for the Cytolux Windows installer.
;
; Inno Setup ships preinstalled on the GitHub windows-latest runners, so the
; workflow calls iscc on this file directly. AppVersion is passed in with /D
; so the version lives in pyproject.toml and nowhere else.
;
;   iscc /DAppVersion=0.3.0 packaging\cytolux.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Cytolux"
#define AppPublisher "Samyabrata Bhaduri"
#define AppExeName "Cytolux.exe"

[Setup]
AppId={{8F3A6C21-4D7B-4E59-9C14-2B5E7A9D6F03}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=
OutputDir=..\installer
OutputBaseFilename=Cytolux-{#AppVersion}-windows-x64-setup
SetupIconFile=..\cytolux\icons\cytolux.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; A per-user install needs no administrator password. Anyone who wants it for the
; whole machine can elevate the installer themselves.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "associate"; Description: "Open .fgw workspaces and .fcs data files with Cytolux"; GroupDescription: "File types:"

[Files]
Source: "..\dist\Cytolux\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.fgw"; ValueType: string; ValueName: ""; ValueData: "Cytolux.Workspace"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\Cytolux.Workspace"; ValueType: string; ValueName: ""; ValueData: "Cytolux workspace"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\Cytolux.Workspace\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\Cytolux.Workspace\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.fcs"; ValueType: string; ValueName: ""; ValueData: "Cytolux.FCS"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\Cytolux.FCS"; ValueType: string; ValueName: ""; ValueData: "Flow cytometry standard data"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\Cytolux.FCS\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\Cytolux.FCS\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: associate

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
