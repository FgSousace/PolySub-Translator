#define MyAppName "PolySub Translator"
#define MyAppVersion "0.4.6"
#define MyAppPublisher "FgSousace"
#define MyAppURL "https://github.com/FgSousace/PolySub-Translator"
#define MyAppExeName "PolySubTranslator.exe"

[Setup]
AppId={{B6B2B2CE-7F64-4E5E-95B0-A1FE45FA74D8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases/latest
DefaultDirName={localappdata}\Programs\PolySub Translator
DefaultGroupName=PolySub Translator
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer-output
OutputBaseFilename=PolySub-Translator-Setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
DisableWelcomePage=yes
UsePreviousAppDir=yes
InfoAfterFile=INSTALLATION.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\PolySubTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "INSTALLATION.txt"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\PolySub Translator"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\PolySub Translator"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\README.txt"; Description: "Otwórz instrukcję README"; Flags: postinstall shellexec skipifsilent unchecked
