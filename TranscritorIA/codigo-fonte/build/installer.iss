; Instalador opcional (Inno Setup 6). A versão portátil é o .zip.
#define AppName "Transcritor IA Local"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B7F3C2E-8A41-4E0B-9C55-71D1A3E9B2F4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Celso Matos Junior
DefaultDirName={autopf}\TranscritorIA
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\TranscritorIA.exe
OutputDir=..\dist-instalador
OutputBaseFilename=TranscritorIA_Setup_{#AppVersion}
SetupIconFile=..\assets\icone.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Files]
Source: "..\dist\TranscritorIA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\TranscritorIA.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\TranscritorIA.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TranscritorIA.exe"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; modelos e configurações ficam em %LOCALAPPDATA%\TranscritorIA e são preservados de propósito
Type: filesandordirs; Name: "{app}\engines"
