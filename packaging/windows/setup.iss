; Inno Setup script for Toolbox (unsigned Windows installer)
; Requires PyInstaller output at ..\dist\Toolbox\

; MyAppVersion is injected by build scripts, e.g.:
;   iscc /DMyAppVersion=0.2.0 packaging/windows/setup.iss
#ifndef MyAppVersion
#define MyAppVersion "dev"
#endif

#define MyAppName "Toolbox"
#define MyAppPublisher "Toolbox"
#define MyAppExeName "Toolbox.exe"

[Setup]
; Never change this GUID: it is how Windows (and Inno Setup) recognise an existing install, so
; this installer upgrades Media Tool 2.x in place instead of installing a second copy next to it.
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Otherwise an upgrade keeps putting the shortcut in the old "Media Tool" Start Menu folder.
UsePreviousGroup=no
OutputDir=..\dist
OutputBaseFilename=Toolbox-Setup-{#MyAppVersion}-win64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\packaging\icons\toolbox.ico
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; The app used to be called Media Tool. When upgrading such an install, remove what the old name
; left behind (the old executable and its shortcuts), which would otherwise stay and point nowhere.
Type: files; Name: "{app}\MediaTool.exe"
Type: files; Name: "{autoprograms}\Media Tool\Media Tool.lnk"
Type: dirifempty; Name: "{autoprograms}\Media Tool"
Type: files; Name: "{autodesktop}\Media Tool.lnk"

[Files]
Source: "..\..\dist\Toolbox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall

[Messages]
; SmartScreen note for friends/family builds
SetupAppTitle=Toolbox Setup
