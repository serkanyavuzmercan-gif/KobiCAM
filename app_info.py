"""
Uygulama kimliği, sürüm ve logo yolları.

Kurulum paketi (PyInstaller) ve kaynak ağaç aynı sabitleri kullanır.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QPixmap

APP_NAME = "KobiCAM"
APP_DISPLAY_NAME = "KobiCAM VMS"
APP_VERSION = "1.2.0"
APP_AUTHOR = "Serkan Yavuz Mercan"
APP_CREDIT = "Serkan Yavuz Mercan tarafından yapılmıştır."
APP_COPYRIGHT = "Tüm hakları saklıdır."
APP_EMAIL = "serkanyavuzmercan@gmail.com"


def kaynak_kok() -> Path:
    """Kaynak dosyalarının kökü (geliştirme veya PyInstaller _MEIPASS)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _ilk_var_olan(adlar: tuple[str, ...]) -> Path | None:
    kok = kaynak_kok()
    for ad in adlar:
        yol = kok / ad
        if yol.is_file():
            return yol
    return None


def logo_yolu() -> Path | None:
    """Pencere ikonu için: çok boyutlu ICO önce gelir."""
    return _ilk_var_olan(("assets/kobicam.ico", "assets/kobicam.png", "assets/kobicam.jpg"))


def logo_resim_yolu() -> Path | None:
    """Ekranda büyük gösterim için: tam çözünürlüklü PNG/JPG önce gelir."""
    return _ilk_var_olan(("assets/kobicam.png", "assets/kobicam.jpg", "assets/kobicam.ico"))


def uygulama_ikonu() -> QIcon:
    yol = logo_yolu()
    return QIcon(str(yol)) if yol else QIcon()


def _piksel_orani(oran: float | None) -> float:
    if oran and oran > 0:
        return float(oran)
    ekran = QGuiApplication.primaryScreen()
    return float(ekran.devicePixelRatio()) if ekran else 1.0


def logo_pixmap(kenar: int = 96, piksel_orani: float | None = None) -> QPixmap:
    """
    Keskin logo döndürür.

    ICO dosyasından okumak küçük kareyi büyüttüğü için bulanıklaşır; bu yüzden
    tam çözünürlüklü PNG tercih edilir ve ekranın piksel oranına göre ölçeklenir.
    """
    yol = logo_resim_yolu()
    if yol is None:
        return QPixmap()
    oran = _piksel_orani(piksel_orani)
    hedef = max(1, int(round(kenar * oran)))

    if yol.suffix.lower() == ".ico":
        pm = QIcon(str(yol)).pixmap(QSize(hedef, hedef))
    else:
        pm = QPixmap(str(yol))
    if pm.isNull():
        return QPixmap()

    if pm.width() != hedef or pm.height() != hedef:
        pm = pm.scaled(
            hedef,
            hedef,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    pm.setDevicePixelRatio(oran)
    return pm
