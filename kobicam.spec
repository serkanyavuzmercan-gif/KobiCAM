# -*- mode: python ; coding: utf-8 -*-
"""KobiCAM VMS — PyInstaller tanımı."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

KOK = Path(SPECPATH).resolve()
IKON = str(KOK / "assets" / "kobicam.ico")

datas = [(str(KOK / "assets"), "assets")]
binaries = []
hiddenimports = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtNetwork",
    "imageio_ffmpeg",
]

for paket in ("imageio_ffmpeg",):
    d, b, h = collect_all(paket)
    datas += d
    binaries += b
    hiddenimports += h

datas += collect_data_files("imageio_ffmpeg")

a = Analysis(
    [str(KOK / "main.py")],
    pathex=[str(KOK)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KobiCAM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=IKON,
    version=str(KOK / "setup" / "file_version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KobiCAM",
)
