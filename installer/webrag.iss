#ifndef AppVersion
  #error AppVersion must be supplied with /DAppVersion=...
#endif

[Setup]
AppId=WebEngineerRAG
AppName=Web Engineer RAG
AppVersion={#AppVersion}
DefaultDirName={userpf}\Web Engineer RAG
DefaultGroupName=Web Engineer RAG
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupIconFile=..\packaging\icon.ico
UninstallDisplayIcon={app}\WebEngineerRAG.exe
OutputDir=..\dist
OutputBaseFilename=WebEngineerRAG-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\dist\WebEngineerRAG\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[Icons]
Name: "{group}\Web Engineer RAG"; Filename: "{app}\WebEngineerRAG.exe"
Name: "{userdesktop}\Web Engineer RAG"; Filename: "{app}\WebEngineerRAG.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WebEngineerRAG.exe"; Description: "Abrir Web Engineer RAG para configurar e indexar"; Flags: nowait postinstall skipifsilent
