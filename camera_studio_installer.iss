; Inno Setup Script for Camera Studio
; Defines installation to Program Files and handles desktop shortcuts

#define AppName "Camera Studio"
#define AppVersion "1.0.0"
#define AppPublisher "Camera Studio Contributors"
#define AppExeName "Camera Studio.exe"

[Setup]
; Unique AppId generated for installer identification
AppId={{C78926AB-1B32-45F4-A0C8-581F7802D96C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=.
OutputBaseFilename=CameraStudioSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Source path points to the build outputs from PyInstaller (dist/main/*)
Source: "dist\main\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstaller}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppExeName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Bersihkan folder data runtime di AppData/Local ketika aplikasi di-uninstall
Type: filesandordirs; Name: "{localappdata}\CameraStudio"
