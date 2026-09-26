; QResolve - Inno Setup script (M7: proper Windows-installed application)
;
; 1. Build the application into the staging dir (repository root):
;      pyinstaller --noconfirm --distpath dist/install --workpath build/install QResolve.spec
;      xcopy /E /I /Q build_package\_python dist\install\QResolve\_python
;    The _python copy is mandatory: PyInstaller's COLLECT step wipes its output
;    directory, and the launcher needs the embedded interpreter beside the exe.
;    build_package\_python must be free of __pycache__ (a .pyc records the
;    absolute path it was compiled from, which would ship the build machine's
;    layout inside the product).
;
; 2. Compile this script:
;      "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\QResolve.iss
;    Bump the release by passing /DMyAppVersion=0.2.0 - filename, AppVersion and
;    the uninstall entry all follow that single knob.
;    /DAppSourceTree="..\dist\QResolve" packages a previously verified build
;    instead of the fresh staging dir.
;
; Output: dist\installer\QResolve Setup <version>.exe
;
; Install mode: PrivilegesRequired=lowest puts the app in the conventional
; per-user location (%LocalAppData%\Programs\QResolve) with no elevation. Run
; the same Setup.exe elevated, or pass /ALLUSERS, and {autopf}/{autoprograms}/
; {autodesktop} retarget to "C:\Program Files\QResolve" for all users instead.

#define MyAppName "QResolve"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "QResolve"
#define MyAppExeName "QResolve.exe"
; Which staged build to package. Default is the installer-ready build; override
; with /DAppSourceTree="..\dist\QResolve" to ship a previously verified tree.
#ifndef AppSourceTree
  #define AppSourceTree "..\dist\install\QResolve"
#endif
#define AppSourceDir AddBackslash(SourcePath) + AppSourceTree

[Setup]
; Fixed for the lifetime of the product. This is what makes a later Setup.exe
; upgrade this installation in place instead of adding a second copy, and what
; keeps the same desktop shortcut across updates. Never regenerate it.
AppId={{08764780-ED4E-41D3-850D-A462EA441F3E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} Setup
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename={#MyAppName} Setup {#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Listed individually on purpose: ISCC fails the build if any of these three is
; missing, so a Setup.exe can never ship without its UI bundle or its embedded
; interpreter.
; DestDir names the directory explicitly for each tree. Using "{app}" alone would
; flatten the contents into the install root - PyInstaller requires _internal as a
; sibling of the exe, and the two interpreter trees share filenames (_tkinter.pyd,
; zlib1.dll, python.exe), so a flat layout would overwrite one with the other.
Source: "{#AppSourceDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppSourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppSourceDir}\_python\*"; DestDir: "{app}\_python"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; A PyInstaller onedir payload is replaced wholesale, never patched: without this
; an update would leave the previous build's modules behind in {app}, and Python
; imports whatever it finds first. Safe to delete because the application writes
; nothing under {app} (its only mutable file is the crash log in %LOCALAPPDATA%).
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\_python"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Deliberately empty. The application writes nothing under {app} - the only file
; it ever writes is its startup crash log in %LOCALAPPDATA%\QResolve (see
; desktop/qresolve_desktop.py:_crash_log_path), and browser-held history lives
; in the user's own profile. Neither is removed here, so a future release that
; does add per-user configuration keeps working across update and uninstall.
