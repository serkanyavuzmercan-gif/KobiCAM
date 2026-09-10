"""
KobiCAM VMS — uygulama giriş noktası.

Sorumluluklar:
  1. Tekil çalışma (single instance) kilidi
  2. İkinci örneği engelleyip mevcut pencereyi öne getirme
  3. İlk kurulum / giriş akışını başlatma
  4. Ana pencereyi açma
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Doğrudan dosya yolundan çalıştırılsa bile paketlerin bulunmasını sağlar
_KOK = Path(__file__).resolve().parent
if str(_KOK) not in sys.path:
    sys.path.insert(0, str(_KOK))

from PyQt6.QtCore import QObject, Qt, QSystemSemaphore, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from app_info import APP_DISPLAY_NAME, APP_NAME, APP_VERSION, uygulama_ikonu
from app_log import get_logger, yakalanmamis_kaydet
from auth_manager import AuthManager
from ui.login_dialog import LoginDialog, SetupWizardDialog
from ui.main_window import MainWindow
from utils.path_helper import configure_ultralytics_offline, ensure_runtime_dirs


# Sistem genelinde benzersiz kilit / soket adı
_APP_KEY = "KobiCAM_VMS_SingleInstance_v1"
_ACTIVATE_MSG = b"ACTIVATE"
# Inno Setup AppMutex ile aynı ad (Win32 CreateMutex; QSystemSemaphore yetmez)
_APP_MUTEX_NAME = "Global\\KobiCAM_VMS_AppMutex"
_app_mutex_handle = None


def _win32_app_mutex() -> None:
    """Kurulumun çalışan KobiCAM.exe'yi görmesi için süreç boyu mutex tutar."""
    global _app_mutex_handle
    if sys.platform != "win32" or _app_mutex_handle:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        _app_mutex_handle = kernel32.CreateMutexW(None, True, _APP_MUTEX_NAME)
    except Exception:
        _app_mutex_handle = None


class SingleInstanceGuard(QObject):
    """
    QSystemSemaphore + QLocalServer ile tekil örnek denetimi.

    Başka bir örnek zaten çalışıyorsa is_running True olur.
    Bu süreç birincil ise, ikinci örneğin bağlantısı activation_requested sinyalini üretir.
    """

    activation_requested = pyqtSignal()

    def __init__(self, anahtar: str = _APP_KEY, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._anahtar = anahtar
        self._semafor = QSystemSemaphore(f"{anahtar}_sem", 1)
        self._sunucu: QLocalServer | None = None
        self.is_running = False

        # İki sürecin aynı anda kilit almasını önlemek için semafor
        self._semafor.acquire()
        try:
            self.is_running = self._baska_ornek_var_mi()
            if not self.is_running:
                self._sunucuyu_baslat()
        finally:
            self._semafor.release()

        if self._sunucu is not None:
            self._sunucu.newConnection.connect(self._yeni_baglanti)

    def _baska_ornek_var_mi(self) -> bool:
        """Yerel sokete bağlanmayı dener; bağlantı kurulursa başka örnek vardır."""
        soket = QLocalSocket()
        soket.connectToServer(self._anahtar)
        baglandi = soket.waitForConnected(150)
        if baglandi:
            soket.disconnectFromServer()
            soket.close()
            return True
        soket.close()
        return False

    def _sunucuyu_baslat(self) -> None:
        """Birincil süreç olarak yerel sunucuyu dinlemeye alır."""
        # Çökme sonrası kalmış soket adını temizle
        QLocalServer.removeServer(self._anahtar)
        self._sunucu = QLocalServer(self)
        if not self._sunucu.listen(self._anahtar):
            # Dinleme başarısızsa güvenli tarafta kal: ikinci örnek gibi davran
            self.is_running = True
            self._sunucu = None

    def _yeni_baglanti(self) -> None:
        """İkinci örneğin 'pencereyi öne getir' isteğini karşılar."""
        if self._sunucu is None:
            return
        soket = self._sunucu.nextPendingConnection()
        if soket is None:
            return
        soket.disconnected.connect(soket.deleteLater)

        def mesaji_isle() -> None:
            veri = bytes(soket.readAll())
            if _ACTIVATE_MSG in veri:
                self.activation_requested.emit()
            soket.disconnectFromServer()

        soket.readyRead.connect(mesaji_isle)
        # readyRead sinyalinden önce veri gelmişse kaçırmamak için hemen oku
        if soket.bytesAvailable() > 0:
            mesaji_isle()

    def notify_existing(self) -> None:
        """Çalışan örneğe öne getirme mesajı gönderir (ikincil süreç)."""
        soket = QLocalSocket()
        soket.connectToServer(self._anahtar)
        if soket.waitForConnected(400):
            soket.write(_ACTIVATE_MSG)
            soket.flush()
            soket.waitForBytesWritten(400)
            soket.disconnectFromServer()
        soket.close()


def _pencereyi_one_getir(pencere: QWidget | None) -> None:
    """Mevcut pencereyi geri yükler ve işletim sistemi odağina alır."""
    if pencere is None:
        return
    pencere.show()
    pencere.setWindowState(
        pencere.windowState() & ~Qt.WindowState.WindowMinimized
    )
    pencere.raise_()
    pencere.activateWindow()

    # Windows, SetForegroundWindow olmadan odağı vermeyebilir
    if sys.platform == "win32":
        try:
            import ctypes

            hwnd = int(pencere.winId())
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def _cökme_kancasi(tur, deger, iz) -> None:
    yakalanmamis_kaydet(tur, deger, iz)
    try:
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.critical(None, APP_DISPLAY_NAME, f"Beklenmeyen hata:\n{deger}")
    except Exception:
        pass


def _thread_kanca(args) -> None:
    yakalanmamis_kaydet(args.exc_type, args.exc_value, args.exc_traceback)


def _unraisable(args) -> None:
    yakalanmamis_kaydet(args.exc_type, args.exc_value, args.exc_traceback)


def main() -> int:
    """Uygulama yaşam döngüsü: kilit → kimlik doğrulama → ana pencere."""
    import threading

    get_logger()
    ensure_runtime_dirs()
    configure_ultralytics_offline()
    _win32_app_mutex()
    sys.excepthook = _cökme_kancasi
    threading.excepthook = _thread_kanca
    sys.unraisablehook = _unraisable

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setWindowIcon(uygulama_ikonu())

    try:
        from security.keychain import KeychainError, master_key

        master_key()
    except KeychainError as hata:
        QMessageBox.critical(None, APP_DISPLAY_NAME, str(hata))
        return 1

    kilit = SingleInstanceGuard()
    if kilit.is_running:
        # İkinci örnek: çalışan pencereyi öne getir ve hemen çık
        kilit.notify_existing()
        return 0

    auth = AuthManager()
    aktif_pencere: QWidget | None = None

    def one_getir() -> None:
        _pencereyi_one_getir(aktif_pencere)

    kilit.activation_requested.connect(one_getir)

    # İlk kurulum veya normal giriş
    if auth.is_first_run():
        dialog: QDialog = SetupWizardDialog(auth)
    else:
        dialog = LoginDialog(auth)

    aktif_pencere = dialog
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return 0

    kullanici = getattr(dialog, "authenticated_user", None)
    if not kullanici:
        return 0

    ana_pencere = MainWindow(kullanici)
    aktif_pencere = ana_pencere
    ana_pencere.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
