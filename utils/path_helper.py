"""
PyInstaller `_MEIPASS` ve `%APPDATA%\\KobiCAM` kaynak yolları.

Dondurulmuş süreçte YOLO ağırlığı internetten indirilmez; paket içindeki
`assets/yolov8n.pt` veya APPDATA kopyası kullanılır.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "KobiCAM"
YOLO_MODEL_NAME = "yolov8n.pt"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Kaynak kökü: PyInstaller geçici dizini veya proje kökü."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    klasor = base / APP_NAME
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def ensure_runtime_dirs() -> Path:
    """logs, models, recordings, faces klasörlerini oluşturur."""
    kok = app_data_dir()
    for ad in ("logs", "models", "recordings", "faces"):
        (kok / ad).mkdir(parents=True, exist_ok=True)
    return kok


def faces_dir() -> Path:
    hedef = app_data_dir() / "faces"
    hedef.mkdir(parents=True, exist_ok=True)
    return hedef


def insightface_root() -> Path:
    """InsightFace kökü: APPDATA/models/insightface (models/buffalo_s altında)."""
    kok = models_dir() / "insightface"
    hedef = kok / "models" / "buffalo_s"
    hedef.mkdir(parents=True, exist_ok=True)
    paket = bundle_root() / "assets" / "insightface" / "buffalo_s"
    gerekli = {"det_500m.onnx", "w600k_mbf.onnx"}
    if paket.is_dir():
        for dosya in paket.iterdir():
            if not dosya.is_file() or dosya.name.lower() not in gerekli:
                continue
            kopya = hedef / dosya.name
            if not kopya.is_file() or kopya.stat().st_size == 0:
                try:
                    shutil.copy2(dosya, kopya)
                except OSError:
                    pass
    return kok


def models_dir() -> Path:
    hedef = app_data_dir() / "models"
    hedef.mkdir(parents=True, exist_ok=True)
    return hedef


def get_resource_path(relative: str | os.PathLike[str]) -> Path:
    """
    Paket (`sys._MEIPASS`), kaynak ağaç veya `%APPDATA%\\KobiCAM` altında
    göreli dosyayı bulur. İlk var olan yolu döndürür; hiçbiri yoksa
    paket kökündeki beklenen yolu verir.
    """
    rel = Path(relative)
    adaylar = [bundle_root() / rel, app_data_dir() / rel]
    if rel.name.lower().endswith(".pt") or (rel.parts and rel.parts[0] == "models"):
        adaylar.append(models_dir() / rel.name)
    for yol in adaylar:
        if yol.exists():
            return yol
    return adaylar[0]


def configure_ultralytics_offline() -> Path:
    """Ultralytics ev dizinine yazmasın ve ilk açılışta model indirmesin."""
    hedef = models_dir()
    os.environ.setdefault("YOLO_CONFIG_DIR", str(hedef))
    os.environ.setdefault("ULTRALYTICS_OFFLINE", "1")
    os.environ.setdefault("YOLO_OFFLINE", "1")
    return hedef


def get_yolo_model_path() -> Path:
    """
    `yolov8n.pt` yolunu döndürür. APPDATA kopyası yoksa paketten kopyalar.
    Dosya yoksa FileNotFoundError — ultralytics isimle çağrılmaz.
    """
    configure_ultralytics_offline()
    hedef = models_dir() / YOLO_MODEL_NAME
    if hedef.is_file() and hedef.stat().st_size > 0:
        return hedef
    paket = bundle_root() / "assets" / YOLO_MODEL_NAME
    if paket.is_file() and paket.stat().st_size > 0:
        try:
            shutil.copy2(paket, hedef)
            return hedef
        except OSError:
            return paket
    raise FileNotFoundError(
        f"YOLOv8 ağırlığı bulunamadı ({paket}). "
        "Kurulum paketine assets/yolov8n.pt eklenmelidir; internet indirmesi kapalıdır."
    )


def get_ffmpeg_path() -> str | None:
    """PATH, paket kökü veya imageio_ffmpeg içindeki ffmpeg.exe."""
    bulunan = shutil.which("ffmpeg")
    if bulunan:
        return bulunan

    kok = bundle_root()
    exe_dir = Path(sys.executable).parent if is_frozen() else kok
    klasor_adaylari = (
        exe_dir,
        kok,
        kok / "imageio_ffmpeg" / "binaries",
        exe_dir / "imageio_ffmpeg" / "binaries",
    )
    for klasor in klasor_adaylari:
        if klasor.is_dir():
            for dosya in klasor.iterdir():
                ad = dosya.name.lower()
                if dosya.is_file() and ad.startswith("ffmpeg") and ad.endswith(".exe"):
                    return str(dosya)

    try:
        import imageio_ffmpeg

        yol = imageio_ffmpeg.get_ffmpeg_exe()
        if yol and Path(yol).is_file():
            return yol
    except Exception:
        pass
    return None
