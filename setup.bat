@echo off
title KobiCAM VMS — kurulum paketi
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\build.ps1"
if errorlevel 1 pause
