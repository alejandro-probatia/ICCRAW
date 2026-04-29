#ifndef RootDir
#define RootDir "..\.."
#endif

#ifndef AppBuildDir
#define AppBuildDir "..\..\dist\windows\ProbRAW"
#endif

#ifndef OutputDir
#define OutputDir "..\..\dist\windows\installer"
#endif

#ifndef AppVersion
#define AppVersion "0.2.5"
#endif

[Setup]
AppId={{F88E3E29-B992-4B88-8BB9-5066D6A77764}
AppName=ProbRAW
AppVersion={#AppVersion}
AppPublisher=Probatia Forensics SL
AppPublisherURL=https://probatia.com
AppSupportURL=https://github.com/alejandro-probatia/ProbRAW
AppUpdatesURL=https://github.com/alejandro-probatia/ProbRAW
DefaultDirName={autopf}\ProbRAW
DefaultGroupName=ProbRAW
DisableProgramGroupPage=yes
LicenseFile={#RootDir}\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=ProbRAW-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#RootDir}\src\probraw\resources\icons\probraw-icon.ico
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
SetupLogging=yes
UninstallDisplayIcon={app}\probraw-ui.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#AppBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RootDir}\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\CHANGELOG.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\LICENSE"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\THIRD_PARTY_LICENSES.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\LEGAL_COMPLIANCE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\AMAZE_GPL3.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\MANUAL_USUARIO.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\METODOLOGIA_COLOR_RAW.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\COLOR_PIPELINE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\DECISIONS.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\PERFORMANCE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\REPRODUCIBILITY.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\docs\WINDOWS_INSTALLER.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#RootDir}\scripts\check_amaze_support.py"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\ProbRAW"; Filename: "{app}\probraw-ui.exe"; WorkingDir: "{app}"; IconFilename: "{app}\probraw-ui.exe"
Name: "{group}\ProbRAW CLI"; Filename: "{cmd}"; Parameters: "/K ""{app}\probraw.exe"" --help"; WorkingDir: "{app}"; IconFilename: "{app}\probraw-ui.exe"
Name: "{group}\Diagnostico herramientas"; Filename: "{cmd}"; Parameters: "/K ""{app}\probraw.exe"" check-tools"; WorkingDir: "{app}"; IconFilename: "{app}\probraw-ui.exe"
Name: "{group}\Desinstalar ProbRAW"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ProbRAW"; Filename: "{app}\probraw-ui.exe"; WorkingDir: "{app}"; IconFilename: "{app}\probraw-ui.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\probraw.exe"; Parameters: "--version"; Flags: runhidden
