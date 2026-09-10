# -*- mode: python ; coding: utf-8 -*-
"""KobiCAM VMS — PyInstaller tanımı (Windows onedir)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

KOK = Path(SPECPATH).resolve()
IKON = str(KOK / "assets" / "kobicam.ico")
YOLO = KOK / "assets" / "yolov8n.pt"
if not YOLO.is_file():
    raise SystemExit(f"Eksik YOLO ağırlığı (datas): {YOLO}")

datas = [(str(KOK / "assets"), "assets")]
web = KOK / "web_static"
if web.is_dir():
    datas.append((str(web), "web_static"))

binaries = []
hiddenimports = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtNetwork",
    "imageio_ffmpeg",
    "imageio_ffmpeg.binaries",
    "jwt",
    "fastapi",
    "uvicorn",
    "googleapiclient",
    "google.auth",
    "google_auth_oauthlib",
    "ultralytics",
    "supervision",
    "cv2",
    "torch",
    "torchvision",
    "scipy",
    "matplotlib",
    "pyngrok",
    "process_util",
    "db_util",
    "app_log",
    "device_reconnector",
    "ui.web_portal_dialog",
    "cryptography",
    "keyring",
    "win32cred",
    "security.keychain",
    "security.crypto_manager",
    "utils",
    "utils.path_helper",
]

for paket in (
    "imageio_ffmpeg",
    "torch",
    "torchvision",
    "ultralytics",
    "cv2",
    "scipy",
    "supervision",
    "fastapi",
    "uvicorn",
    "googleapiclient",
):
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
