; KobiCAM Server Gateway — Inno Setup 6
; Derlemek için: build_server.bat

#define MyAppName "KobiCAM Server Gateway"
#define MyAppVersion "1.0"
#define MyAppPublisher "Serkan Yavuz Mercan"
#define MyAppCopyright "Tüm hakları saklıdır."
#define MyAppExeName "KobiCAM-Server.exe"

[Setup]
AppId={{B8D5F3C2-0A1E-4D9B-9C7F-2E4A6B8C1D3F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright={#MyAppCopyright}
DefaultDirName={autopf}\KobiCAM-Server
DefaultGroupName=KobiCAM
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=KobiCAM-Server-Setup-1.0
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
AppMutex=Global\KobiCAM_Server_Gateway
SetupMutex=KobiCAM_Server_Setup

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; GroupDescription: "Ek görevler:"; Flags: unchecked
Name: "startup"; Description: "Windows açılışında başlat"; GroupDescription: "Ek görevler:"; Flags: unchecked

[Dirs]
Name: "{userappdata}\KobiCAM"; Flags: uninsneveruninstall
Name: "{userappdata}\KobiCAM\logs"; Flags: uninsneveruninstall

[Files]
Source: "..\dist\KobiCAM-Server\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\KobiCAM\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Uzak HLS yayın ağ geçidi"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} başlat"; Flags: nowait postinstall skipifsilent

[Messages]
turkish.WelcomeLabel1=KobiCAM Server Gateway kurulumuna hoş geldiniz
turkish.WelcomeLabel2=Bu sihirbaz [name/ver] yazılımını kuracaktır. Saat yanında çalışır; masaüstü VMS kapanınca yayın kesilmez.%n%nSerkan Yavuz Mercan tarafından yapılmıştır.

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM KobiCAM-Server.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
