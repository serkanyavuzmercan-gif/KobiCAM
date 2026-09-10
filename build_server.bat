@echo off
setlocal EnableExtensions
title KobiCAM Server Gateway — derleme
cd /d "%~dp0"

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" (
  call "%~dp0.venv\Scripts\activate.bat"
  set "PY=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
  call "%~dp0venv\Scripts\activate.bat"
  set "PY=%~dp0venv\Scripts\python.exe"
)

if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 (
    set "PY=py"
  ) else (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
  )
)

if not defined PY (
  echo Python bulunamadi.
  exit /b 1
)

if not exist "%~dp0KobiCAM-Server.spec" (
  echo KobiCAM-Server.spec yok.
  exit /b 1
)

echo ==^> PyInstaller Server
"%PY%" -m PyInstaller --noconfirm --clean "%~dp0KobiCAM-Server.spec"
if errorlevel 1 (
  echo PyInstaller basarisiz.
  exit /b 1
)

if not exist "%~dp0dist\KobiCAM-Server\KobiCAM-Server.exe" (
  echo Beklenen exe yok: dist\KobiCAM-Server\KobiCAM-Server.exe
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
  echo Inno Setup 6 yok. dist\KobiCAM-Server hazir.
  echo Setup icin: winget install JRSoftware.InnoSetup
  exit /b 1
)

echo ==^> Inno Setup Server
"%ISCC%" "%~dp0setup\KobiCAM-Server.iss"
if errorlevel 1 (
  echo Inno Setup basarisiz.
  exit /b 1
)

echo.
echo Kurulum: setup\Output\KobiCAM-Server-Setup-1.0.exe
endlocal
