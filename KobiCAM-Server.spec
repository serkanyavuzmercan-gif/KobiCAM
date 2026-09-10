# -*- mode: python ; coding: utf-8 -*-
"""KobiCAM Server Gateway — PyInstaller (onedir, torch yok)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

KOK = Path(SPECPATH).resolve()
IKON = str(KOK / "assets" / "kobicam.ico")

datas = []
web = KOK / "web_static"
if web.is_dir():
    datas.append((str(web), "web_static"))
assets = KOK / "assets" / "kobicam.ico"
if assets.is_file():
    datas.append((str(KOK / "assets"), "assets"))

binaries = []
hiddenimports = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "imageio_ffmpeg",
    "imageio_ffmpeg.binaries",
    "jwt",
    "fastapi",
    "uvicorn",
    "psutil",
    "process_util",
    "db_util",
    "app_log",
    "cryptography",
    "keyring",
    "win32cred",
    "winreg",
    "security.keychain",
    "security.crypto_manager",
    "utils",
    "utils.path_helper",
    "utils.network_helper",
    "web_server",
    "web_token",
    "config_manager",
    "auth_manager",
]

for paket in ("imageio_ffmpeg", "fastapi", "uvicorn"):
    try:
        d, b, h = collect_all(paket)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

datas += collect_data_files("imageio_ffmpeg")

try:
    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_yol = Path(ffmpeg_exe) if ffmpeg_exe else None
    if ffmpeg_yol is not None and ffmpeg_yol.is_file():
        binaries.append((str(ffmpeg_yol), "."))
        binaries.append((str(ffmpeg_yol), "imageio_ffmpeg/binaries"))
except Exception:
    pass

a = Analysis(
    [str(KOK / "server_app.py")],
    pathex=[str(KOK)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchvision", "ultralytics", "cv2", "matplotlib", "googleapiclient"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KobiCAM-Server",
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
    name="KobiCAM-Server",
)
