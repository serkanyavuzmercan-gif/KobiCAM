"""
KobiCAM Server Gateway — penceresiz system tray HLS sunucusu.

VMS ile aynı %APPDATA%\\KobiCAM config.json / users.db dosyalarını okur.
Ana grafik penceresi açılmaz.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

_KOK = Path(__file__).resolve().parent
if str(_KOK) not in sys.path:
    sys.path.insert(0, str(_KOK))

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QWidget,
)

from app_info import APP_NAME, uygulama_ikonu
from app_log import get_logger, yakalanmamis_kaydet
from config_manager import ConfigManager
from utils.network_helper import get_tailscale_ip, portal_url
from utils.path_helper import ensure_runtime_dirs
from web_server import WebServerThread

_log = get_logger("server")

_SUNUCU_SURUM = "1.0"
_MUTEX_AD = "Global\\KobiCAM_Server_Gateway"
_RUN_ANAHTAR = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_DEGER = "KobiCAMServer"
_app_mutex_handle = None


def _win32_mutex() -> bool:
    """True: bu süreç mutex'i aldı. False: başka örnek zaten çalışıyor."""
    global _app_mutex_handle
    if sys.platform != "win32":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.GetLastError.restype = ctypes.c_ulong
        _app_mutex_handle = kernel32.CreateMutexW(None, True, _MUTEX_AD)
        return int(kernel32.GetLastError()) != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def _calistirma_komutu() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'


def acilista_var_mi() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_ANAHTAR) as k:
            winreg.QueryValueEx(k, _RUN_DEGER)
        return True
    except OSError:
        return False


def acilisa_yaz(acik: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_ANAHTAR, 0, winreg.KEY_SET_VALUE
    ) as k:
        if acik:
            winreg.SetValueEx(k, _RUN_DEGER, 0, winreg.REG_SZ, _calistirma_komutu())
        else:
            try:
                winreg.DeleteValue(k, _RUN_DEGER)
            except OSError:
                pass


class ServerTray(QWidget):
    """Saat yanı simgesi; ana pencere gösterilmez."""

    def __init__(self) -> None:
        super().__init__()
        self.hide()
        self._hazir = False
        self._config = ConfigManager()
        self._isci: WebServerThread | None = None
        self._url = ""
        self._teppsi: QSystemTrayIcon | None = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(
                None,
                "KobiCAM Server",
                "Sistem tepsisi yok; Gateway başlatılamadı.",
            )
            QTimer.singleShot(0, QApplication.instance().quit)
            return

        self._teppsi = QSystemTrayIcon(uygulama_ikonu() or QIcon(), self)
        self._teppsi.setToolTip("KobiCAM Server Gateway")
        self._menu = QMenu()
        self._baslik = QAction(f"KobiCAM Server Gateway v{_SUNUCU_SURUM}", self)
        self._baslik.setEnabled(False)
        self._durum = QAction("Bağlantı Yok", self)
        self._durum.setEnabled(False)
        self._kopya = QAction("Erişim Bağlantısını Kopyala", self)
        self._kopya.triggered.connect(self._adres_kopyala)
        self._servis = QAction("Servisi Durdur", self)
        self._servis.triggered.connect(self._servis_degistir)
        self._acilisa = QAction("Windows Açılışına Ekle", self)
        self._acilisa.setCheckable(True)
        self._acilisa.setChecked(acilista_var_mi())
        self._acilisa.toggled.connect(acilisa_yaz)
        self._cikis = QAction("Çıkış", self)
        self._cikis.triggered.connect(self._cik)
        self._menu.addAction(self._baslik)
        self._menu.addSeparator()
        self._menu.addAction(self._durum)
        self._menu.addAction(self._kopya)
        self._menu.addAction(self._servis)
        self._menu.addSeparator()
        self._menu.addAction(self._acilisa)
        self._menu.addAction(self._cikis)
        self._teppsi.setContextMenu(self._menu)
        self._teppsi.show()
        self._hazir = True

        self._zaman = QTimer(self)
        self._zaman.timeout.connect(self._yenile)
        self._zaman.start(2000)
        self._baslat()
        self._yenile()

    def _baslat(self) -> None:
        if self._isci is not None and self._isci.isRunning():
            return
        self._durdur()
        try:
            self._config.load()
        except Exception:
            _log.exception("config")
        self._isci = WebServerThread(self._config, self)
        self._isci.url_hazir.connect(self._url_al)
        self._isci.hata.connect(lambda m: _log.warning("%s", m))
        self._isci.start()
        self._servis.setText("Servisi Durdur")

    def _durdur(self) -> None:
        if self._isci is None:
            self._url = ""
            return
        self._isci.request_stop()
        self._isci.wait(4000)
        self._isci = None
        self._url = ""
        self._servis.setText("Servisi Başlat")

    def _servis_degistir(self) -> None:
        if self._isci is not None and self._isci.isRunning():
            self._durdur()
        else:
            self._baslat()
        self._yenile()

    def _url_al(self, url: str) -> None:
        self._url = url or ""
        self._yenile()

    def _portal(self) -> str:
        port = int(self._config.get("web_port") or 8765)
        return portal_url(port) or self._url or ""

    def _yenile(self) -> None:
        try:
            self._config.load()
        except Exception:
            pass
        calisiyor = self._isci is not None and self._isci.isRunning()
        ts = get_tailscale_ip()
        if self._teppsi is None:
            return
        if calisiyor and ts:
            self._durum.setText(f"Yayın Aktif (Tailscale: {ts})")
            self._teppsi.setToolTip(f"KobiCAM Server — {ts}")
        elif calisiyor:
            self._durum.setText("Yayın Aktif (Tailscale yok)")
            self._teppsi.setToolTip("KobiCAM Server — Tailscale yok")
        else:
            self._durum.setText("Bağlantı Yok")
            self._teppsi.setToolTip("KobiCAM Server — durdu")
        self._kopya.setEnabled(bool(self._portal()))

    def _adres_kopyala(self) -> None:
        adres = self._portal()
        if not adres:
            self._teppsi.showMessage(
                "KobiCAM Server",
                "Adres yok. Tailscale açık olsun ve servis çalışsın.",
                QSystemTrayIcon.MessageIcon.Warning,
                4000,
            )
            return
        QApplication.clipboard().setText(adres)
        self._teppsi.showMessage(
            "KobiCAM Server",
            f"Kopyalandı: {adres}",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _cik(self) -> None:
        self._zaman.stop()
        self._durdur()
        if self._teppsi is not None:
            self._teppsi.hide()
        QApplication.instance().quit()


def main() -> int:
    ensure_runtime_dirs()
    if not _win32_mutex():
        return 0

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("KobiCAM Server Gateway")
    app.setWindowIcon(uygulama_ikonu())

    sys.excepthook = lambda t, d, i: yakalanmamis_kaydet(t, d, i)

    teppsi = ServerTray()
    if not getattr(teppsi, "_hazir", False):
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
