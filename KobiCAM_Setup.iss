; KobiCAM VMS — Inno Setup 6
; Derlemek için: build_release.bat  veya  ISCC.exe KobiCAM_Setup.iss

#define MyAppName "KobiCAM VMS"
#define MyAppVersion "1.2.2"
#define MyAppPublisher "Serkan Yavuz Mercan"
#define MyAppCopyright "Tüm hakları saklıdır."
#define MyAppExeName "KobiCAM.exe"

[Setup]
AppId={{A7C4E2B1-9F3D-4C8A-B6E5-1D2F8A9C0B7E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright={#MyAppCopyright}
AppPublisherURL=
DefaultDirName={autopf}\KobiCAM
DefaultGroupName=KobiCAM
DisableProgramGroupPage=yes
OutputDir=setup\Output
OutputBaseFilename=KobiCAM-Setup-1.2.2
SetupIconFile=assets\kobicam.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardImageFile=setup\wizard-large.bmp
WizardSmallImageFile=setup\wizard-small.bmp
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
AppMutex=Global\KobiCAM_VMS_AppMutex
SetupMutex=KobiCAM_Setup

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; GroupDescription: "Ek görevler:"; Flags: unchecked

[Dirs]
Name: "{userappdata}\KobiCAM"; Flags: uninsneveruninstall
Name: "{userappdata}\KobiCAM\logs"; Flags: uninsneveruninstall
Name: "{userappdata}\KobiCAM\models"; Flags: uninsneveruninstall
Name: "{userappdata}\KobiCAM\recordings"; Flags: uninsneveruninstall

[Files]
Source: "dist\KobiCAM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\yolov8n.pt"; DestDir: "{userappdata}\KobiCAM\models"; DestName: "yolov8n.pt"; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\KobiCAM\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Kamera izleme yazılımı"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} uygulamasını başlat"; Flags: nowait postinstall skipifsilent

[Messages]
turkish.WelcomeLabel1=KobiCAM VMS kurulumuna hoş geldiniz
turkish.WelcomeLabel2=Bu sihirbaz [name/ver] yazılımını bilgisayarınıza kuracaktır.%n%nSerkan Yavuz Mercan tarafından yapılmıştır. Tüm hakları saklıdır.%n%nDevam etmeden önce diğer uygulamaları kapatmanız önerilir.

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM KobiCAM.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
