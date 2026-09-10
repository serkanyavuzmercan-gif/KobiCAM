@echo off
setlocal EnableExtensions
title KobiCAM VMS — release derlemesi
cd /d "%~dp0"

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" (
  call "%~dp0.venv\Scripts\activate.bat"
  set "PY=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
  call "%~dp0venv\Scripts\activate.bat"
  set "PY=%~dp0venv\Scripts\python.exe"
) else if exist "%~dp0env\Scripts\python.exe" (
  call "%~dp0env\Scripts\activate.bat"
  set "PY=%~dp0env\Scripts\python.exe"
)

if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 (
    set "PY=py"
  ) else (
    where python >nul 2>&1
    if not errorlevel 1 (
      set "PY=python"
    )
  )
)

if not defined PY (
  echo Python 3.10+ bulunamadi. python.org adresinden kurun.
  exit /b 1
)

if not exist "%~dp0KobiCAM.spec" (
  echo KobiCAM.spec bulunamadi.
  exit /b 1
)

echo ==^> OpenCV GUI paketini kaldir (headless kalsin)
"%PY%" -m pip uninstall -y opencv-python opencv-contrib-python >nul 2>&1

echo ==^> PyInstaller
"%PY%" -m PyInstaller --noconfirm --clean "%~dp0KobiCAM.spec"
if errorlevel 1 (
  echo PyInstaller basarisiz.
  exit /b 1
)

if not exist "%~dp0dist\KobiCAM\KobiCAM.exe" (
  echo Beklenen exe yok: dist\KobiCAM\KobiCAM.exe
  exit /b 1
)

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  where iscc >nul 2>&1
  if not errorlevel 1 set "ISCC=iscc"
)

if not defined ISCC (
  echo Inno Setup 6 bulunamadi. dist\KobiCAM klasoru hazir.
  echo Setup.exe icin: winget install JRSoftware.InnoSetup
  exit /b 1
)

echo ==^> Inno Setup
"%ISCC%" "%~dp0KobiCAM_Setup.iss"
if errorlevel 1 (
  echo Inno Setup derlemesi basarisiz.
  exit /b 1
)

echo.
echo Kurulum: setup\Output\KobiCAM-Setup-1.2.2.exe
endlocal
