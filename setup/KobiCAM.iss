; KobiCAM VMS — Inno Setup 6
; Derlemek için: setup\build.ps1  veya  ISCC.exe setup\KobiCAM.iss

#define MyAppName "KobiCAM VMS"
#define MyAppVersion "1.1.2"
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
OutputBaseFilename=KobiCAM-Setup-{#MyAppVersion}
SetupIconFile=..\assets\kobicam.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardImageFile=wizard-large.bmp
WizardSmallImageFile=wizard-small.bmp
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; GroupDescription: "Ek görevler:"; Flags: unchecked

[Files]
Source: "..\dist\KobiCAM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\KobiCAM\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Kamera izleme yazılımı"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} uygulamasını başlat"; Flags: nowait postinstall skipifsilent

[Messages]
turkish.WelcomeLabel1=KobiCAM VMS kurulumuna hoş geldiniz
turkish.WelcomeLabel2=Bu sihirbaz [name/ver] yazılımını bilgisayarınıza kuracaktır.%n%nSerkan Yavuz Mercan tarafından yapılmıştır. Tüm hakları saklıdır.%n%nDevam etmeden önce diğer uygulamaları kapatmanız önerilir.
