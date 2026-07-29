; installer.iss
; compile with:  iscc /DAppVersion=1.0.0 installer.iss
; AppId must stay fixed forever — it is how future installers upgrade the existing install
; instead of creating a second copy. Generate your own once with Tools > Generate GUID in the
; Inno Setup IDE if you like, but never change it after the first release.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8F3A2B1C-4D5E-4F6A-9B7C-1E2D3F4A5B6C}}
AppName=Patient History Analyzer
AppVersion={#AppVersion}
DefaultDirName={autopf}\PatientHistoryAnalyzer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=PatientHistoryAnalyzer-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\PatientHistoryAnalyzer\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{autoprograms}\Patient History Analyzer"; Filename: "{app}\PatientHistoryAnalyzer.exe"
Name: "{autodesktop}\Patient History Analyzer"; Filename: "{app}\PatientHistoryAnalyzer.exe"

[Run]
Filename: "{app}\PatientHistoryAnalyzer.exe"; Description: "Launch Patient History Analyzer"; Flags: nowait postinstall skipifsilent