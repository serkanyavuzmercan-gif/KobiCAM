; KobiCAM VMS — Inno Setup 6 (setup\ altından derleme)
; Kanonik script: ..\KobiCAM_Setup.iss
; Derlemek için: ..\build_release.bat  veya  ISCC.exe ..\KobiCAM_Setup.iss

#define MyAppName "KobiCAM VMS"
#define MyAppVersion "1.4.0"
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
OutputDir=Output
OutputBaseFilename=KobiCAM-Setup-1.4.0
SetupIconFile=..\assets\kobicam.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardImageFile=wizard-large.bmp
WizardSmallImageFile=wizard-small.bmp
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
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
Name: "{userappdata}\KobiCAM"; Flags: uninsneveruninstall
Name: "{userappdata}\KobiCAM\logs"; Flags: uninsneveruninstall
Name: "{userappdata}\KobiCAM\models"; Flags: uninsneveruninstall
Name: "{userappdata}\KobiCAM\recordings"; Flags: uninsneveruninstall
Name: "{userappdata}\KobiCAM\faces"; Flags: uninsneveruninstall

[Files]
Source: "..\dist\KobiCAM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\yolov8n.pt"; DestDir: "{userappdata}\KobiCAM\models"; DestName: "yolov8n.pt"; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\KobiCAM\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Kamera izleme / Camera monitoring"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[Messages]
turkish.WelcomeLabel1=KobiCAM VMS kurulumuna hoş geldiniz
turkish.WelcomeLabel2=Bu sihirbaz [name/ver] yazılımını bilgisayarınıza kuracaktır.%n%nSerkan Yavuz Mercan tarafından yapılmıştır. Tüm hakları saklıdır.%n%nYüz tanıma, kişi yönetimi ve yüz dışa/içe aktarma bu sürümde yer alır.%n%nDevam etmeden önce diğer uygulamaları kapatmanız önerilir.
english.WelcomeLabel1=Welcome to the KobiCAM VMS Setup Wizard
english.WelcomeLabel2=This will install [name/ver] on your computer.%n%nCreated by Serkan Yavuz Mercan. All rights reserved.%n%nThis version includes face recognition, person management, and face gallery export/import.%n%nIt is recommended that you close other applications before continuing.

[CustomMessages]
turkish.LaunchApp=KobiCAM VMS uygulamasını başlat
english.LaunchApp=Launch KobiCAM VMS

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM KobiCAM.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
