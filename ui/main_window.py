"""
Ana uygulama penceresi.

Sol kamera listesi, dinamik ızgara, ağ tarama ve tam ekran (F11) burada birleşir.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QByteArray,
    QEvent,
    QMetaObject,
    QMimeData,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QDrag,
    QIcon,
    QKeySequence,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, APP_EMAIL, logo_pixmap, uygulama_ikonu

from config_manager import ConfigManager
from network_scanner import NetworkScanner, yerel_ipv4_adresleri
from onvif_media import cihaz_baglan, cihaz_tani
from rtsp_probe import SABLONLAR, kanallari_uret
from ui.about_dialog import AboutDialog
from ui.add_camera_dialog import AddCameraDialog
from ui.add_device_dialog import AddDeviceDialog
from ui.camera_grid import CameraGrid
from ui.bar_icons import ikon_buyut, ikon_kapat, ikon_kucult
from ui.camera_widget import KAMERA_MIME
from ui.help_dialog import HelpDialog, ShortcutsDialog
from ui.settings_dialog import SettingsDialog


_STIL = """
QMainWindow, QWidget#root { background-color: #12151a; }
QMenuBar {
    background-color: #1a1d23;
    color: #e8edf5;
}
QMenuBar::item:selected { background-color: #2b7fc4; }
QMenu {
    background-color: #1a1d23;
    color: #e8edf5;
    border: 1px solid #2e3440;
    padding: 4px;
}
/* Sağ dolgu olmadan kısayol metni öğe adının üstüne biniyor. */
QMenu::item {
    padding: 6px 28px 6px 28px;
    min-width: 180px;
}
QMenu::item:selected { background-color: #2b7fc4; }
QMenu::item:disabled { color: #6b7383; }
QMenu::separator { height: 1px; background-color: #2e3440; margin: 4px 8px; }
QStatusBar { background-color: #1a1d23; color: #8b95a8; }
QSplitter::handle { background-color: #2e3440; width: 2px; }
QListWidget {
    background-color: #0b0d10;
    color: #e8edf5;
    border: none;
    outline: none;
}
QListWidget::item { padding: 8px 10px; }
QListWidget::item:selected { background-color: #2b7fc4; }
QListWidget::item:hover { background-color: #1e2530; }
QLabel#panelTitle {
    color: #8b95a8;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 8px 10px 4px 10px;
}
QToolButton {
    background-color: #1a1d23;
    color: #c5cdd8;
    border: 1px solid #2e3440;
    border-radius: 4px;
    padding: 4px 10px;
}
QToolButton:hover { border-color: #3d9cf0; color: #e8edf5; }
QWidget#pencere { background-color: #12151a; border: 1px solid #2e3440; }
QWidget#titleBar { background-color: #1a1d23; }
QMenuBar { background-color: transparent; }
QToolButton#winLogo {
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 0;
}
QToolButton#winLogo:hover { background-color: #2b3038; }
QToolButton#winBtn {
    background-color: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
}
QToolButton#winBtn:hover { background-color: #2b3038; }
QToolButton#winClose:hover { background-color: #c42b2b; }
"""

# Kenardan tutup boyutlandırma için ayrılan çerçeve kalınlığı
_KENAR = 6


class _BaslikCubugu(QWidget):
    """Yerleşik pencere çubuğu: logo, başlık, menü ve pencere düğmeleri."""

    def __init__(self, pencere: QMainWindow, menu_cubugu: QMenuBar) -> None:
        super().__init__(pencere)
        self._pencere = pencere
        self.setObjectName("titleBar")
        self.setFixedHeight(34)

        yerlesim = QHBoxLayout(self)
        yerlesim.setContentsMargins(8, 0, 0, 0)
        yerlesim.setSpacing(8)

        logo = QToolButton(self)
        logo.setObjectName("winLogo")
        pm = logo_pixmap(20, self.devicePixelRatioF())
        if not pm.isNull():
            logo.setIcon(QIcon(pm))
        logo.setIconSize(QSize(20, 20))
        logo.setFixedSize(30, 30)
        logo.setCursor(Qt.CursorShape.PointingHandCursor)
        logo.setToolTip("Hakkında")
        logo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        logo.clicked.connect(lambda: AboutDialog(pencere).exec())
        yerlesim.addWidget(logo)

        yerlesim.addWidget(menu_cubugu)
        yerlesim.addStretch(1)

        self._btn_kucult = self._pencere_dugmesi(ikon_kucult(), "Küçült")
        self._btn_kucult.clicked.connect(pencere.showMinimized)
        self._btn_buyut = self._pencere_dugmesi(ikon_buyut(False), "Büyüt")
        self._btn_buyut.clicked.connect(self.buyut_degistir)
        self._btn_kapat = self._pencere_dugmesi(ikon_kapat(), "Kapat")
        self._btn_kapat.setObjectName("winClose")
        self._btn_kapat.clicked.connect(pencere.close)
        for dugme in (self._btn_kucult, self._btn_buyut, self._btn_kapat):
            yerlesim.addWidget(dugme)

    def _pencere_dugmesi(self, ikon, ipucu: str) -> QToolButton:
        dugme = QToolButton(self)
        dugme.setObjectName("winBtn")
        dugme.setIcon(ikon)
        dugme.setIconSize(QSize(16, 16))
        dugme.setToolTip(ipucu)
        dugme.setFixedSize(44, 34)
        dugme.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return dugme

    def buyut_degistir(self) -> None:
        if self._pencere.isMaximized():
            self._pencere.showNormal()
        else:
            self._pencere.showMaximized()

    def durumu_yenile(self) -> None:
        tam = self._pencere.isMaximized()
        self._btn_buyut.setIcon(ikon_buyut(tam))
        self._btn_buyut.setToolTip("Eski boyut" if tam else "Büyüt")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            tutamac = self._pencere.windowHandle()
            if tutamac is not None:
                tutamac.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.buyut_degistir()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class CameraListWidget(QListWidget):
    """Kamerayı ızgara hücresine sürüklemek için MIME üretir."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def startDrag(self, supported_actions) -> None:  # noqa: N802 — Qt API
        oge = self.currentItem()
        if oge is None:
            return
        kamera = oge.data(Qt.ItemDataRole.UserRole) or {}
        kamera_id = str(kamera.get("id") or "")
        if not kamera_id:
            return
        mime = QMimeData()
        mime.setData(KAMERA_MIME, QByteArray(kamera_id.encode("utf-8")))
        surukle = QDrag(self)
        surukle.setMimeData(mime)
        surukle.exec(Qt.DropAction.CopyAction)


class _KanalKesif(QThread):
    """ONVIF / RTSP ile DVR kameralarını arka planda okur."""

    bitti = pyqtSignal(dict)

    def __init__(self, cihaz: dict, parent=None) -> None:
        super().__init__(parent)
        self._cihaz = dict(cihaz)

    def run(self) -> None:
        sonuc = cihaz_baglan(
            str(self._cihaz.get("ip") or ""),
            str(self._cihaz.get("username") or ""),
            str(self._cihaz.get("password") or ""),
            str(self._cihaz.get("xaddrs") or ""),
            str(self._cihaz.get("name") or self._cihaz.get("ip") or ""),
            int(self._cihaz.get("onvif_port") or 80),
            int(self._cihaz.get("port") or 554),
            str(self._cihaz.get("vendor") or "auto"),
            int(self._cihaz.get("media_port") or 0),
        )
        sonuc["device_id"] = str(self._cihaz.get("id") or "")
        self.bitti.emit(sonuc)


class MainWindow(QMainWindow):
    """Kimlik doğrulama sonrası açılan ana VMS penceresi."""

    def __init__(self, username: str, parent=None) -> None:
        super().__init__(parent)
        self._username = username
        self._tam_ekran = False
        self._config = ConfigManager()
        self._tarama_aktif = False
        self._kanal_isci: _KanalKesif | None = None
        self._kanal_taban: dict | None = None

        self.setWindowTitle(f"{APP_DISPLAY_NAME} — {username}")
        self.setWindowIcon(uygulama_ikonu())
        self.resize(1280, 720)
        self.setMinimumSize(800, 500)
        self.setStyleSheet(_STIL)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMouseTracking(True)

        self._menu_cubugu = QMenuBar()
        self._arayuz_kur()
        self._tarayici_kur()
        self._menu_olustur()

        durum = QStatusBar()
        durum.showMessage(f"Oturum: {username}")
        self.setStatusBar(durum)

        self._listeyi_yenile()
        self._cihaz_listesini_yenile()
        self._medya_uygula()
        self._slotlari_yukle()
        self._yerlesimi_geri_yukle()

    def _arayuz_kur(self) -> None:
        kok = QWidget()
        kok.setObjectName("root")
        yerlesim = QHBoxLayout(kok)
        yerlesim.setContentsMargins(0, 0, 0, 0)
        yerlesim.setSpacing(0)
        self._govde = kok

        ayirici = QSplitter(Qt.Orientation.Horizontal)

        sol = QWidget()
        sol_y = QVBoxLayout(sol)
        sol_y.setContentsMargins(0, 0, 0, 8)
        sol_y.setSpacing(6)

        cihaz_baslik = QLabel("CİHAZLAR")
        cihaz_baslik.setObjectName("panelTitle")
        sol_y.addWidget(cihaz_baslik)

        cihaz_dugme = QHBoxLayout()
        cihaz_dugme.setContentsMargins(8, 0, 8, 0)
        self._btn_cihaz = QToolButton()
        self._btn_cihaz.setText("Cihaz Ekle")
        self._btn_cihaz.clicked.connect(self._cihaz_ekle)
        self._btn_tara = QToolButton()
        self._btn_tara.setText("Ağı Tara")
        self._btn_tara.clicked.connect(self._agi_tara)
        cihaz_dugme.addWidget(self._btn_cihaz)
        cihaz_dugme.addWidget(self._btn_tara)
        cihaz_dugme.addStretch(1)
        sol_y.addLayout(cihaz_dugme)

        self._cihaz_liste = QListWidget()
        self._cihaz_liste.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._cihaz_liste.itemDoubleClicked.connect(self._cihaz_cift_tik)
        self._cihaz_liste.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._cihaz_liste.customContextMenuRequested.connect(self._cihaz_menu)
        self._cihaz_liste.setMaximumHeight(160)
        sol_y.addWidget(self._cihaz_liste)

        kamera_baslik = QLabel("KAMERALAR")
        kamera_baslik.setObjectName("panelTitle")
        sol_y.addWidget(kamera_baslik)

        kamera_dugme = QHBoxLayout()
        kamera_dugme.setContentsMargins(8, 0, 8, 0)
        self._btn_duzenle = QToolButton()
        self._btn_duzenle.setText("Düzenle")
        self._btn_duzenle.clicked.connect(self._secili_kamerayi_duzenle)
        kamera_dugme.addWidget(self._btn_duzenle)
        kamera_dugme.addStretch(1)
        sol_y.addLayout(kamera_dugme)

        self._liste = CameraListWidget()
        self._liste.itemDoubleClicked.connect(self._liste_cift_tik)
        self._liste.itemClicked.connect(self._liste_tek_tik)
        self._liste.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._liste.customContextMenuRequested.connect(self._liste_menu)
        sol_y.addWidget(self._liste, 1)
        sol.setMinimumWidth(200)
        sol.setMaximumWidth(360)

        duzen = int(self._config.get("grid_layout", 4) or 4)
        self._izgara = CameraGrid(duzen)
        for i, hucre in enumerate(self._izgara.widgets()):
            hucre.camera_dropped.connect(
                lambda cid, idx=i: self._hucreye_birak(cid, idx)
            )
            hucre.snapshot_saved.connect(self._snapshot_bildir)
            hucre.record_toggled.connect(self._kayit_bildir)
            hucre.record_failed.connect(self._kayit_hata)
            hucre.audio_failed.connect(self._ses_hata)
            hucre.quality_changed.connect(self._kamera_kalite_kaydet)

        ayirici.addWidget(sol)
        ayirici.addWidget(self._izgara)
        ayirici.setStretchFactor(0, 0)
        ayirici.setStretchFactor(1, 1)
        ayirici.setCollapsible(0, True)
        ayirici.setCollapsible(1, False)
        ayirici.setSizes([240, 1040])
        self._sol = sol
        self._ayirici = ayirici
        self._splitter_boyut = [240, 1040]

        yerlesim.addWidget(ayirici)

        self._baslik_cubugu = _BaslikCubugu(self, self._menu_cubugu)
        pencere = QWidget()
        pencere.setObjectName("pencere")
        dis = QVBoxLayout(pencere)
        dis.setContentsMargins(_KENAR, _KENAR, _KENAR, _KENAR)
        dis.setSpacing(0)
        dis.addWidget(self._baslik_cubugu)
        dis.addWidget(kok, 1)
        self._dis_yerlesim = dis
        self.setCentralWidget(pencere)

    def _tarayici_kur(self) -> None:
        self._scan_thread = QThread(self)
        self._scanner = NetworkScanner()
        self._scanner.moveToThread(self._scan_thread)
        self._scanner.camera_found.connect(self._kamera_bulundu)
        self._scanner.scan_progress.connect(self._tarama_ilerleme)
        self._scanner.scan_finished.connect(self._tarama_bitti)
        self._scanner.scan_error.connect(self._tarama_hatasi)
        self._scan_thread.start()

    def _komut(
        self,
        menu: QMenu,
        metin: str,
        kisayol: str,
        islev,
        *,
        secilebilir: bool = False,
        isaretli: bool = False,
    ) -> QAction:
        """Menüye kısayollu bir komut ekler."""
        aksiyon = QAction(metin, self)
        if kisayol:
            aksiyon.setShortcut(QKeySequence(kisayol))
            aksiyon.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        if secilebilir:
            aksiyon.setCheckable(True)
            aksiyon.setChecked(isaretli)
        aksiyon.triggered.connect(islev)
        menu.addAction(aksiyon)
        return aksiyon

    def _menu_olustur(self) -> None:
        menü = self._menu_cubugu

        dosya = menü.addMenu("Dosya")
        self._komut(
            dosya, "Kullanıcı ayarlarını kaydet", "Ctrl+S", self._kullanici_ayarlarini_kaydet
        )
        dosya.addSeparator()
        self._komut(dosya, "Kayıt klasörünü aç", "Ctrl+Shift+K", self._kayit_klasorunu_ac)
        self._komut(
            dosya, "Anlık görüntü klasörünü aç", "Ctrl+Shift+G", self._gorsel_klasorunu_ac
        )
        dosya.addSeparator()
        self._komut(dosya, "Çıkış", "Ctrl+Q", self.close)

        gorunum = menü.addMenu("Görünüm")
        grup = QActionGroup(self)
        grup.setExclusive(True)
        self._duzen_aksiyonlari: dict[int, QAction] = {}
        mevcut = int(self._config.get("grid_layout", 4) or 4)
        duzenler = ((1, "1'li", "Ctrl+1"), (4, "4'lü", "Ctrl+2"), (9, "9'lu", "Ctrl+3"),
                    (16, "16'lı", "Ctrl+4"))
        for sayi, etiket, ks in duzenler:
            aksiyon = self._komut(
                gorunum,
                f"{etiket} ızgara",
                ks,
                lambda checked=False, n=sayi: self._duzen_sec(n),
                secilebilir=True,
                isaretli=sayi == mevcut,
            )
            grup.addAction(aksiyon)
            self._duzen_aksiyonlari[sayi] = aksiyon

        gorunum.addSeparator()
        kalite_grup = QActionGroup(self)
        kalite_grup.setExclusive(True)
        self._kalite_aksiyonlari: dict[str, QAction] = {}
        mevcut_k = self._config.display_quality()
        kaliteler = (("low", "Düşük kalite (SD)", "Ctrl+Shift+D"),
                     ("high", "Yüksek kalite (HD)", "Ctrl+Shift+H"))
        for anahtar, etiket, ks in kaliteler:
            aksiyon = self._komut(
                gorunum,
                etiket,
                ks,
                lambda checked=False, k=anahtar: self._kalite_sec(k),
                secilebilir=True,
                isaretli=anahtar == mevcut_k,
            )
            kalite_grup.addAction(aksiyon)
            self._kalite_aksiyonlari[anahtar] = aksiyon

        gorunum.addSeparator()
        self._tam_ekran_aksiyon = self._komut(
            gorunum, "Tam Ekran", "F11", self._tam_ekran_degistir, secilebilir=True
        )

        cihazlar = menü.addMenu("Cihazlar")
        self._komut(cihazlar, "Cihaz Ekle…", "Ctrl+N", self._cihaz_ekle)
        self._tara_aksiyon = self._komut(cihazlar, "Ağı Tara", "F5", self._agi_tara)
        cihazlar.addSeparator()
        self._komut(cihazlar, "Seçili cihaza bağlan", "Ctrl+B", self._secili_cihaza_baglan)
        self._komut(
            cihazlar, "Kanalları elle ekle…", "Ctrl+Shift+N", self._secili_cihaz_kanal_elle
        )
        self._komut(cihazlar, "Seçili cihazı tanıla", "F8", self._secili_cihazi_tanila)
        self._komut(cihazlar, "Seçili cihazı düzenle…", "F2", self._secili_cihazi_duzenle)
        self._komut(cihazlar, "Seçili cihazı sil", "Ctrl+Shift+Del", self._secili_cihazi_sil)

        kameralar = menü.addMenu("Kameralar")
        self._komut(kameralar, "Manuel RTSP kamera…", "Ctrl+M", self._kamera_ekle)
        self._komut(
            kameralar, "Seçili kamerayı hücreye bağla", "Ctrl+Return", self._secili_kamerayi_ata
        )
        self._komut(
            kameralar, "Seçili kamerayı düzenle…", "Shift+F2", self._secili_kamerayi_duzenle
        )
        self._komut(kameralar, "Seçili kamerayı sil", "Shift+Del", self._secili_kamerayi_sil)
        kameralar.addSeparator()
        self._komut(kameralar, "Anlık görüntü al", "Ctrl+P", self._hucre_anlik_goruntu)
        self._komut(kameralar, "Kaydı başlat / durdur", "Ctrl+R", self._hucre_kayit)
        self._komut(kameralar, "Canlı sesi aç / kapat", "Ctrl+U", self._hucre_ses)
        self._komut(kameralar, "Hücre kalitesini değiştir", "Ctrl+E", self._hucre_kalite)
        self._komut(kameralar, "Yakınlaştırmayı sıfırla", "Ctrl+0", self._hucre_zoom_sifirla)
        kameralar.addSeparator()
        self._komut(kameralar, "Seçili hücreyi boşalt", "Ctrl+Del", self._hucre_bosalt)

        ayarlar = menü.addMenu("Ayarlar")
        self._komut(ayarlar, "Tercihler…", "Ctrl+,", self._ayarlari_ac)

        yardim = menü.addMenu("Yardım")
        self._komut(yardim, "Nasıl çalışır?", "F1", self._yardim_ac)
        self._komut(yardim, "Klavye kısayolları", "Ctrl+F1", self._kisayollari_ac)
        self._komut(yardim, f"İletişim — {APP_EMAIL}", "Shift+F1", self._iletisim)

    # ------------------------------------------------------------------
    # Seçili ızgara hücresi üzerinde çalışan kısayol komutları
    # ------------------------------------------------------------------

    def _secili_hucre(self):
        """Seçili ızgara hücresini döndürür; kamera yoksa None."""
        hucreler = self._izgara.widgets()
        indeks = self._izgara.selected_index()
        if not (0 <= indeks < len(hucreler)):
            return None
        hucre = hucreler[indeks]
        if hucre.camera is None:
            self.statusBar().showMessage("Önce bir hücreye kamera atayın.", 4000)
            return None
        return hucre

    def _hucre_anlik_goruntu(self) -> None:
        hucre = self._secili_hucre()
        if hucre is not None:
            hucre.snapshot()

    def _hucre_kayit(self) -> None:
        hucre = self._secili_hucre()
        if hucre is not None:
            hucre.toggle_recording()

    def _hucre_ses(self) -> None:
        hucre = self._secili_hucre()
        if hucre is not None:
            hucre.toggle_audio()

    def _hucre_kalite(self) -> None:
        hucre = self._secili_hucre()
        if hucre is not None:
            hucre.toggle_quality()

    def _hucre_zoom_sifirla(self) -> None:
        hucre = self._secili_hucre()
        if hucre is not None:
            hucre.reset_zoom()

    def _hucre_bosalt(self) -> None:
        indeks = self._izgara.selected_index()
        if 0 <= indeks < len(self._izgara.widgets()):
            self._izgara.assign_camera(indeks, None)
            self._slotlari_kaydet()

    def _secili_cihaz(self) -> dict | None:
        """Cihaz listesinde seçili kaydı döndürür."""
        oge = self._cihaz_liste.currentItem()
        if oge is None:
            self.statusBar().showMessage("Önce listeden bir cihaz seçin.", 4000)
            return None
        return oge.data(Qt.ItemDataRole.UserRole) or None

    def _secili_cihaza_baglan(self) -> None:
        cihaz = self._secili_cihaz()
        if cihaz is not None:
            self._kanallari_sorgula(cihaz)

    def _secili_cihazi_duzenle(self) -> None:
        cihaz = self._secili_cihaz()
        if cihaz is not None:
            self._cihaz_dialog(cihaz)

    def _secili_cihaz_kanal_elle(self) -> None:
        cihaz = self._secili_cihaz()
        if cihaz is not None:
            self._kanallari_elle_olustur(cihaz)

    def _secili_cihazi_sil(self) -> None:
        cihaz = self._secili_cihaz()
        if cihaz is not None:
            self._cihazi_sil(cihaz)

    def _secili_kamera_ogesi(self) -> QListWidgetItem | None:
        """Kameralar listesinde seçili öğeyi döndürür."""
        oge = self._liste.currentItem()
        if oge is None:
            self.statusBar().showMessage("Önce Kameralar listesinden birini seçin.", 4000)
            return None
        return oge

    def _secili_kamerayi_ata(self) -> None:
        oge = self._secili_kamera_ogesi()
        if oge is not None:
            self._liste_cift_tik(oge)

    def _secili_kamerayi_duzenle(self) -> None:
        oge = self._secili_kamera_ogesi()
        if oge is not None:
            self._kamera_dialog(oge.data(Qt.ItemDataRole.UserRole) or {})

    def _secili_kamerayi_sil(self) -> None:
        oge = self._secili_kamera_ogesi()
        if oge is not None:
            self._kamerayi_sil(oge.data(Qt.ItemDataRole.UserRole) or {})

    def _medya_uygula(self) -> None:
        """Kayıt klasörü, format ve akış tercihlerini hücrelere işler."""
        klasor = self._config.media_dir()
        gorsel = self._config.snapshot_dir()
        snap = str(self._config.get("snapshot_format") or "png")
        rec = str(self._config.get("record_format") or "mp4")
        for hucre in self._izgara.widgets():
            hucre.set_media_options(klasor, snap, rec, gorsel)
        self._izgara.akislari_uygula(self._prefer_sub(), self._main_on_zoom())

    def _klasor_ac(self, klasor) -> None:
        klasor.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(klasor)))
        self.statusBar().showMessage(f"Klasör açıldı: {klasor}")

    def _kayit_klasorunu_ac(self) -> None:
        self._klasor_ac(self._config.media_dir())

    def _gorsel_klasorunu_ac(self) -> None:
        self._klasor_ac(self._config.snapshot_dir())

    def _kullanici_ayarlarini_kaydet(self, sessiz: bool = False) -> None:
        """Pencere yerleşimi, ızgara düzeni ve hücre atamalarını diske yazar."""
        self._config.set("grid_layout", self._izgara.layout_count, kaydet=False)
        self._config.set(
            "window_geometry",
            bytes(self.saveGeometry().toBase64()).decode("ascii"),
            kaydet=False,
        )
        if not self._tam_ekran:
            self._config.set("splitter_sizes", self._ayirici.sizes(), kaydet=False)
        self._slotlari_kaydet(kaydet=False)
        self._config.save()
        self.statusBar().showMessage("Kullanıcı ayarları kaydedildi.")
        if not sessiz:
            QMessageBox.information(
                self,
                "Ayarlar",
                "Pencere düzeni, ızgara ve kamera yerleşimi kaydedildi.",
            )

    def _yerlesimi_geri_yukle(self) -> None:
        ham = str(self._config.get("window_geometry") or "")
        if ham:
            self.restoreGeometry(QByteArray.fromBase64(ham.encode("ascii")))
        boyutlar = self._config.get("splitter_sizes") or []
        if isinstance(boyutlar, list) and len(boyutlar) == 2:
            temiz = [int(x) for x in boyutlar if int(x) >= 0]
            if len(temiz) == 2 and sum(temiz) > 0:
                self._ayirici.setSizes(temiz)
                self._splitter_boyut = temiz

    def _kalite_sec(self, kalite: str) -> None:
        """Görünüm menüsünden genel kaliteyi anında uygular."""
        self._config.set_display_quality(kalite)
        self._kalite_aksiyon_isaretle(kalite)
        self._izgara.akislari_uygula(self._prefer_sub(), self._main_on_zoom())

    def _kalite_aksiyon_isaretle(self, kalite: str) -> None:
        aksiyon = self._kalite_aksiyonlari.get(kalite)
        if aksiyon is not None:
            aksiyon.setChecked(True)

    def _kamera_kalite_kaydet(self, kamera: dict) -> None:
        self._config.upsert_camera(kamera, from_scan=False)

    def _slotlari_kaydet(self, kaydet: bool = True) -> None:
        ids: list[str] = []
        for hucre in self._izgara.widgets():
            kamera = hucre.camera
            ids.append(str(kamera.get("id") or "") if kamera else "")
        self._config.set("grid_slots", ids, kaydet=kaydet)

    def _slotlari_yukle(self) -> None:
        """Kayıtlı hücre yerleşimini (veya URL'si olan kameraları) yayına bağlar."""
        slots = self._config.grid_slots()
        url_olan = [
            c for c in self._config.cameras() if (c.get("main_url") or "").strip()
        ]
        if not any(slots):
            for i, kamera in enumerate(url_olan[: self._izgara.layout_count]):
                self._izgara.assign_camera(i, kamera)
            if url_olan:
                self._slotlari_kaydet()
                self.statusBar().showMessage("Kayıtlı kameralar bağlandı.")
            else:
                self.statusBar().showMessage("Cihaz Ekle ile DVR/NVR bağlayın; kameralar burada listelenir.")
            return
        baglanan = 0
        for i, kid in enumerate(slots[:16]):
            if not kid:
                continue
            kamera = self._config.camera_by_id(kid)
            if kamera and (kamera.get("main_url") or "").strip():
                self._izgara.assign_camera(i, kamera)
                baglanan += 1
        if baglanan:
            self.statusBar().showMessage(f"{baglanan} kayıtlı kamera bağlandı.")
        else:
            self.statusBar().showMessage("Cihaz Ekle ile DVR/NVR bağlayın; kameralar listelenir.")

    def _hakkinda(self) -> None:
        AboutDialog(self).exec()

    def _yardim_ac(self) -> None:
        HelpDialog(self).exec()

    def _kisayollari_ac(self) -> None:
        ShortcutsDialog(self).exec()

    def _iletisim(self) -> None:
        QDesktopServices.openUrl(QUrl(f"mailto:{APP_EMAIL}"))
        self.statusBar().showMessage(f"İletişim: {APP_EMAIL}")

    def _ayarlari_ac(self) -> None:
        dialog = SettingsDialog(self._config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._medya_uygula()
        sayi = int(self._config.get("grid_layout", 4) or 4)
        self._duzen_sec(sayi)
        self._kalite_aksiyon_isaretle(self._config.display_quality())

    def _snapshot_bildir(self, yol: str) -> None:
        self.statusBar().showMessage(f"Anlık görüntü kaydedildi: {yol}")

    def _kayit_bildir(self, aktif: bool) -> None:
        if aktif:
            self.statusBar().showMessage("Kayıt başladı (passthrough, re-encode yok).")
        else:
            self.statusBar().showMessage("Kayıt durdu.")

    def _kayit_hata(self, mesaj: str) -> None:
        self.statusBar().showMessage(f"Kayıt hatası: {mesaj}")
        QMessageBox.warning(self, "Kayıt", mesaj)

    def _ses_hata(self, mesaj: str) -> None:
        self.statusBar().showMessage(f"Ses: {mesaj}")

    def _prefer_sub(self) -> bool:
        return self._config.display_quality() == "low"

    def _main_on_zoom(self) -> bool:
        return bool(self._config.get("main_stream_on_zoom", True))

    def _duzen_sec(self, sayi: int) -> None:
        self._izgara.set_layout_count(sayi)
        self._izgara.akislari_uygula(self._prefer_sub(), self._main_on_zoom())
        self._config.set("grid_layout", sayi)
        aksiyon = self._duzen_aksiyonlari.get(sayi)
        if aksiyon is not None:
            aksiyon.setChecked(True)

    def _tam_ekran_degistir(self) -> None:
        """Tam ekranda yalnızca kamera ızgarası kalır (sol panel ve menü gizlenir)."""
        self._tam_ekran = not self._tam_ekran
        self._tam_ekran_aksiyon.setChecked(self._tam_ekran)
        if self._tam_ekran:
            self._splitter_boyut = self._ayirici.sizes()
            self._buyuktu = self.isMaximized()
            self._sol.hide()
            self._baslik_cubugu.hide()
            self.statusBar().hide()
            self._izgara.set_tam_ekran(True)
            self._dis_kenar(0)
            self.showFullScreen()
        else:
            self._baslik_cubugu.show()
            self.statusBar().show()
            self._sol.show()
            self._ayirici.setSizes(self._splitter_boyut or [240, 1040])
            self._izgara.set_tam_ekran(False)
            if getattr(self, "_buyuktu", False):
                self.showMaximized()
            else:
                self.showNormal()

    def _dis_kenar(self, kalinlik: int) -> None:
        self._dis_yerlesim.setContentsMargins(kalinlik, kalinlik, kalinlik, kalinlik)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "_baslik_cubugu"):
            self._baslik_cubugu.durumu_yenile()
            # Büyütülmüş/tam ekran pencerede boyutlandırma bandına gerek yok
            self._dis_kenar(0 if (self.isMaximized() or self.isFullScreen()) else _KENAR)

    def _kenar_bul(self, pos) -> Qt.Edge | None:
        """İmlecin pencere kenarına denk gelip gelmediğini bulur."""
        if self.isMaximized() or self.isFullScreen():
            return None
        kenarlar = []
        if pos.x() <= _KENAR:
            kenarlar.append(Qt.Edge.LeftEdge)
        elif pos.x() >= self.width() - _KENAR:
            kenarlar.append(Qt.Edge.RightEdge)
        if pos.y() <= _KENAR:
            kenarlar.append(Qt.Edge.TopEdge)
        elif pos.y() >= self.height() - _KENAR:
            kenarlar.append(Qt.Edge.BottomEdge)
        if not kenarlar:
            return None
        sonuc = kenarlar[0]
        for kenar in kenarlar[1:]:
            sonuc = sonuc | kenar
        return sonuc

    @staticmethod
    def _kenar_imleci(kenar) -> Qt.CursorShape:
        sol = bool(kenar & Qt.Edge.LeftEdge)
        sag = bool(kenar & Qt.Edge.RightEdge)
        ust = bool(kenar & Qt.Edge.TopEdge)
        alt = bool(kenar & Qt.Edge.BottomEdge)
        if (sol and ust) or (sag and alt):
            return Qt.CursorShape.SizeFDiagCursor
        if (sag and ust) or (sol and alt):
            return Qt.CursorShape.SizeBDiagCursor
        if sol or sag:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def mouseMoveEvent(self, event) -> None:
        kenar = self._kenar_bul(event.position().toPoint())
        if kenar is None:
            self.unsetCursor()
        else:
            self.setCursor(self._kenar_imleci(kenar))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            kenar = self._kenar_bul(event.position().toPoint())
            tutamac = self.windowHandle()
            if kenar is not None and tutamac is not None:
                tutamac.startSystemResize(kenar)
                event.accept()
                return
        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:
        self.unsetCursor()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._tam_ekran:
            self._tam_ekran_degistir()
            event.accept()
            return
        super().keyPressEvent(event)

    def _agi_tara(self) -> None:
        if self._tarama_aktif:
            return
        self._tarama_aktif = True
        self._tara_aksiyon.setEnabled(False)
        self._btn_tara.setEnabled(False)
        self.statusBar().showMessage("Ağ taranıyor…")
        QMetaObject.invokeMethod(
            self._scanner,
            "start_scan",
            Qt.ConnectionType.QueuedConnection,
        )

    def _kamera_bulundu(self, ip: str, port: int, kaynak: str, bilgi: dict) -> None:
        portlar = [int(p) for p in ((bilgi or {}).get("ports") or [])]
        uretici = "auto"
        onvif_port = 80
        if 34567 in portlar or 8899 in portlar:
            uretici = "xm"
            onvif_port = 8899 if 8899 in portlar else 80
        elif 37777 in portlar:
            uretici = "dahua"
        elif 8000 in portlar:
            uretici = "hikvision"
        kayit = {
            "name": (bilgi or {}).get("name") or ip,
            "ip": ip,
            "port": port,
            "onvif_port": onvif_port,
            "media_port": 34567 if 34567 in portlar else 0,
            "username": "",
            "password": "",
            "source": kaynak,
            "xaddrs": (bilgi or {}).get("xaddrs") or "",
            "vendor": uretici,
        }
        self._config.upsert_device(kayit, from_scan=True)
        self._cihaz_listesini_yenile()

    def _tarama_ilerleme(self, mevcut: int, toplam: int) -> None:
        if toplam <= 0:
            self.statusBar().showMessage("ONVIF keşfi…")
            return
        self.statusBar().showMessage(f"RTSP taranıyor: {mevcut}/{toplam}")

    def _tarama_bitti(self) -> None:
        self._tarama_aktif = False
        self._tara_aksiyon.setEnabled(True)
        self._btn_tara.setEnabled(True)
        sayi = len(self._config.devices())
        aglar = ", ".join(
            f"{'.'.join(ip.split('.')[:3])}.x" for ip in yerel_ipv4_adresleri()
        )
        mesaj = f"Tarama tamamlandı — {sayi} cihaz."
        if aglar:
            mesaj += f" Taranan ağlar: {aglar}"
        self.statusBar().showMessage(mesaj)

    def _tarama_hatasi(self, mesaj: str) -> None:
        self.statusBar().showMessage(f"Tarama hatası: {mesaj}")

    def _cihaz_listesini_yenile(self) -> None:
        secili_id = ""
        oge = self._cihaz_liste.currentItem()
        if oge is not None:
            secili_id = str((oge.data(Qt.ItemDataRole.UserRole) or {}).get("id") or "")
        self._cihaz_liste.clear()
        yeni: QListWidgetItem | None = None
        for cihaz in self._config.devices():
            ad = str(cihaz.get("name") or cihaz.get("ip") or "Cihaz")
            ip = str(cihaz.get("ip") or "")
            kam_sayi = len(self._config.cameras_of_device(str(cihaz.get("id") or "")))
            if not (cihaz.get("username") or "").strip():
                etiket = f"{ad}\n{ip}  · şifre bekliyor"
            elif kam_sayi:
                etiket = f"{ad}\n{ip}  · {kam_sayi} kamera"
            else:
                etiket = f"{ad}\n{ip}  · bağlanmadı"
            item = QListWidgetItem(etiket)
            item.setData(Qt.ItemDataRole.UserRole, cihaz)
            item.setSizeHint(QSize(0, 44))
            item.setToolTip(f"{ad}\n{ip}\nKaynak: {cihaz.get('source') or '-'}")
            self._cihaz_liste.addItem(item)
            if cihaz.get("id") == secili_id:
                yeni = item
        if yeni is not None:
            self._cihaz_liste.setCurrentItem(yeni)

    def _listeyi_yenile(self) -> None:
        secili_id = ""
        oge = self._liste.currentItem()
        if oge is not None:
            secili_id = str((oge.data(Qt.ItemDataRole.UserRole) or {}).get("id") or "")
        self._liste.clear()
        yeni_secim: QListWidgetItem | None = None
        kameralar = [
            k for k in self._config.cameras() if (k.get("main_url") or "").strip()
        ]
        for kamera in kameralar:
            ad = str(kamera.get("name") or kamera.get("ip") or "Kamera")
            ip = str(kamera.get("ip") or "")
            etiket = f"{ad}\n{ip}"
            item = QListWidgetItem(etiket)
            item.setData(Qt.ItemDataRole.UserRole, kamera)
            item.setSizeHint(QSize(0, 44))
            ipucu = f"{ad}\n{ip}:{kamera.get('port', 554)}"
            if kamera.get("channel"):
                ipucu += f"\nKanal {kamera.get('channel')}"
            item.setToolTip(ipucu)
            self._liste.addItem(item)
            if kamera.get("id") == secili_id:
                yeni_secim = item
        if yeni_secim is not None:
            self._liste.setCurrentItem(yeni_secim)

    def _liste_tek_tik(self, item: QListWidgetItem) -> None:
        kamera = item.data(Qt.ItemDataRole.UserRole) or {}
        if (kamera.get("main_url") or "").strip():
            self.statusBar().showMessage("Kamerayı bir hücreye sürükleyin veya çift tıklayın.")
        else:
            self.statusBar().showMessage("Bu kayıtta yayın adresi yok.")

    def _secili_kamerayi_duzenle(self) -> None:
        oge = self._liste.currentItem()
        if oge is None:
            QMessageBox.information(
                self,
                "Kamera",
                "Soldan bir kamera seçin. DVR bağlamak için Cihaz Ekle kullanın.",
            )
            return
        self._kamera_dialog(oge.data(Qt.ItemDataRole.UserRole) or {})

    def _liste_cift_tik(self, item: QListWidgetItem) -> None:
        kamera = item.data(Qt.ItemDataRole.UserRole) or {}
        kamera = self._url_gerekirse_duzenle(kamera)
        if kamera is None:
            return
        self._izgara.assign_to_selected_or_empty(kamera)
        self._slotlari_kaydet()

    def _hucreye_birak(self, kamera_id: str, indeks: int) -> None:
        """Sürükleme bittikten sonra bağlar (DND sırasında diyalog/akış süreci kapatır)."""
        QTimer.singleShot(50, lambda: self._hucreye_bagla(kamera_id, indeks))

    def _hucreye_bagla(self, kamera_id: str, indeks: int) -> None:
        try:
            kamera = self._config.camera_by_id(kamera_id)
            if kamera is None:
                return
            kamera = self._url_gerekirse_duzenle(kamera)
            if kamera is None:
                return
            self._izgara.assign_camera(indeks, kamera)
            self._slotlari_kaydet()
        except Exception as hata:
            QMessageBox.warning(self, "Kamera", f"Hücreye bağlanırken hata: {hata}")

    def _url_gerekirse_duzenle(self, kamera: dict) -> dict | None:
        if (kamera.get("main_url") or "").strip():
            return kamera
        QMessageBox.information(
            self,
            "Yayın yok",
            "Bu kameranın RTSP adresi yok. Cihazı yeniden bağlayın veya Manuel RTSP kullanın.",
        )
        return self._kamera_dialog(kamera)

    def _cihaz_ekle(self) -> None:
        self._cihaz_dialog(None)

    def _secili_cihazi_tanila(self) -> None:
        oge = self._cihaz_liste.currentItem()
        if oge is None:
            QMessageBox.information(self, "Cihaz", "Önce Cihazlar listesinden bir cihaz seçin.")
            return
        self._cihaz_tanila(oge.data(Qt.ItemDataRole.UserRole) or {})

    def _cihaz_cift_tik(self, item: QListWidgetItem) -> None:
        self._cihaz_dialog(item.data(Qt.ItemDataRole.UserRole) or {})

    def _cihaz_dialog(self, cihaz: dict | None) -> dict | None:
        dialog = AddDeviceDialog(cihaz, self)
        if dialog.exec() != dialog.DialogCode.Accepted or not dialog.sonuc:
            return None
        kayit = self._config.upsert_device(dialog.sonuc, from_scan=False)
        self._cihaz_listesini_yenile()
        self._kanallari_sorgula(kayit)
        return kayit

    def _cihaz_menu(self, pos) -> None:
        oge = self._cihaz_liste.itemAt(pos)
        menu = QMenu(self)
        if oge is None:
            ekle = menu.addAction("Cihaz Ekle…")
            secim = menu.exec(self._cihaz_liste.mapToGlobal(pos))
            if secim == ekle:
                self._cihaz_ekle()
            return
        cihaz = oge.data(Qt.ItemDataRole.UserRole) or {}
        baglan = menu.addAction("Bağlan / kameraları oku\tCtrl+B")
        elle = menu.addAction("Kanalları elle ekle…\tCtrl+Shift+N")
        tani = menu.addAction("Tanıla\tF8")
        duzenle = menu.addAction("Düzenle…\tF2")
        sil = menu.addAction("Cihazı sil\tCtrl+Shift+Del")
        secim = menu.exec(self._cihaz_liste.mapToGlobal(pos))
        if secim == baglan:
            if not (cihaz.get("username") or "").strip():
                self._cihaz_dialog(cihaz)
            else:
                self._kanallari_sorgula(cihaz)
        elif secim == elle:
            self._kanallari_elle_olustur(cihaz)
        elif secim == tani:
            self._cihaz_tanila(cihaz)
        elif secim == duzenle:
            self._cihaz_dialog(cihaz)
        elif secim == sil:
            self._cihazi_sil(cihaz)

    def _cihazi_sil(self, cihaz: dict) -> None:
        """Cihazı ve ona bağlı kameraları siler."""
        cid = str(cihaz.get("id") or "")
        if not cid:
            return
        ad = str(cihaz.get("name") or cihaz.get("ip") or "cihaz")
        onay = QMessageBox.question(
            self,
            "Cihazı sil",
            f"{ad} ve bu cihaza bağlı kameralar listeden silinsin mi?",
        )
        if onay != QMessageBox.StandardButton.Yes:
            return
        silinen = self._config.remove_device(cid)
        for i, hucre in enumerate(self._izgara.widgets()):
            mevcut = hucre.camera
            if mevcut and mevcut.get("id") in silinen:
                self._izgara.assign_camera(i, None)
        self._cihaz_listesini_yenile()
        self._listeyi_yenile()
        self._slotlari_kaydet()

    def _kamera_ekle(self) -> None:
        self._kamera_dialog(None)

    def _kamera_dialog(self, kamera: dict | None) -> dict | None:
        dialog = AddCameraDialog(kamera, self)
        if dialog.exec() != dialog.DialogCode.Accepted or not dialog.sonuc:
            return None
        kayit = self._config.upsert_camera(dialog.sonuc, from_scan=False)
        self._listeyi_yenile()
        self._bagli_hucreleri_guncelle(kayit)
        return kayit

    def _kanallari_sorgula(self, kayit: dict) -> None:
        if self._kanal_isci is not None and self._kanal_isci.isRunning():
            QMessageBox.information(self, "Cihaz", "Başka bir cihaz hâlâ okunuyor. Lütfen bekleyin.")
            return
        self._kanal_taban = dict(kayit)
        self.statusBar().showMessage("Cihazdaki kameralar okunuyor…")
        self._kanal_bekleyici = QProgressDialog(
            "Kayıt cihazındaki kameralar okunuyor…",
            None,
            0,
            0,
            self,
        )
        self._kanal_bekleyici.setWindowTitle(APP_DISPLAY_NAME)
        self._kanal_bekleyici.setCancelButton(None)
        self._kanal_bekleyici.setMinimumDuration(300)
        self._kanal_bekleyici.setWindowModality(Qt.WindowModality.WindowModal)
        self._kanal_isci = _KanalKesif(kayit, self)
        self._kanal_isci.bitti.connect(self._kanallar_geldi)
        self._kanal_isci.start()

    def _kanallar_geldi(self, sonuc: dict) -> None:
        bekleyici = getattr(self, "_kanal_bekleyici", None)
        if bekleyici is not None:
            bekleyici.close()
            self._kanal_bekleyici = None
        taban = self._kanal_taban or {}
        cihaz_id = str(sonuc.get("device_id") or taban.get("id") or "")
        kanallar = sonuc.get("kanallar") or []
        if sonuc.get("xaddrs"):
            guncel = dict(taban)
            guncel["xaddrs"] = sonuc.get("xaddrs")
            if cihaz_id:
                guncel["id"] = cihaz_id
            self._config.upsert_device(guncel, from_scan=False)
        if not sonuc.get("ok") or not kanallar:
            self._cihaz_listesini_yenile()
            mesaj = str(sonuc.get("hata") or "Kamera listesi alınamadı.")
            self.statusBar().showMessage(mesaj)
            self._baglanti_hatasi(taban, mesaj, sonuc.get("gunluk") or [])
            return
        # Bulunan port ve üretici bir sonraki bağlanmayı hızlandırsın
        degisti = False
        if sonuc.get("rtsp_port") and int(sonuc["rtsp_port"]) != int(taban.get("port") or 554):
            taban["port"] = int(sonuc["rtsp_port"])
            degisti = True
        bulunan_uretici = str(sonuc.get("vendor") or "")
        if bulunan_uretici and bulunan_uretici != "auto" and taban.get("vendor") in ("", None, "auto"):
            taban["vendor"] = bulunan_uretici
            degisti = True
        if degisti:
            self._config.upsert_device(taban, from_scan=False)
        yazilan = self._kanallari_yaz(taban, cihaz_id, kanallar, sonuc.get("xaddrs") or "")
        QMessageBox.information(
            self,
            "Cihaz",
            f"{len(yazilan)} kamera bulundu.\n"
            "Kameralar listesinden istediğiniz kanalı ızgara hücresine sürükleyin.",
        )

    def _kanallari_yaz(
        self,
        cihaz: dict,
        cihaz_id: str,
        kanallar: list,
        xaddrs: str = "",
    ) -> list[dict]:
        ip = str(cihaz.get("ip") or "")
        hazir = [
            {
                **ch,
                "ip": ip,
                "port": cihaz.get("port") or 554,
                "username": cihaz.get("username") or "",
                "password": cihaz.get("password") or "",
                "xaddrs": xaddrs or cihaz.get("xaddrs") or "",
                "source": cihaz.get("source") or "onvif",
                "device_id": cihaz_id,
            }
            for ch in kanallar
        ]
        yazilan = self._config.uygula_kanallar(ip, hazir, device_id=cihaz_id)
        self._listeyi_yenile()
        self._cihaz_listesini_yenile()
        for kayit in yazilan:
            self._bagli_hucreleri_guncelle(kayit)
        self.statusBar().showMessage(
            f"{len(yazilan)} kamera listelendi. Soldan hücreye sürükleyin."
        )
        return yazilan

    def _baglanti_hatasi(self, cihaz: dict, mesaj: str, gunluk: list) -> None:
        """Bağlanamama nedenini gösterir ve elle kanal / tanılama seçeneği sunar."""
        kutu = QMessageBox(self)
        kutu.setIcon(QMessageBox.Icon.Warning)
        kutu.setWindowTitle("Cihaz bağlantısı")
        kutu.setText(mesaj)
        if gunluk:
            kutu.setDetailedText("\n".join(str(x) for x in gunluk))
        elle = kutu.addButton("Kanalları elle ekle…", QMessageBox.ButtonRole.AcceptRole)
        tani = kutu.addButton("Tanıla", QMessageBox.ButtonRole.ActionRole)
        kutu.addButton("Kapat", QMessageBox.ButtonRole.RejectRole)
        kutu.exec()
        if kutu.clickedButton() is elle:
            self._kanallari_elle_olustur(cihaz)
        elif kutu.clickedButton() is tani:
            self._cihaz_tanila(cihaz)

    def _cihaz_tanila(self, cihaz: dict) -> None:
        self.statusBar().showMessage("Cihaz sınanıyor…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            satirlar = cihaz_tani(
                str(cihaz.get("ip") or ""),
                str(cihaz.get("username") or ""),
                str(cihaz.get("password") or ""),
                int(cihaz.get("onvif_port") or 80),
                int(cihaz.get("port") or 554),
                int(cihaz.get("media_port") or 0),
            )
        finally:
            QApplication.restoreOverrideCursor()
        self.statusBar().showMessage("Tanılama tamamlandı.")
        kutu = QMessageBox(self)
        kutu.setIcon(QMessageBox.Icon.Information)
        kutu.setWindowTitle("Cihaz tanılama")
        kutu.setText(f"{cihaz.get('ip') or ''} sonuçları")
        kutu.setInformativeText("\n".join(satirlar))
        kutu.exec()

    def _kanallari_elle_olustur(self, cihaz: dict) -> None:
        """Otomatik bulunamayan cihazlarda kanalları şablondan üretir."""
        ip = str(cihaz.get("ip") or "")
        if not ip:
            return
        etiketler = [f"{s[1]}  ({s[2].format(n=1, u='kullanici', p='sifre')})" for s in SABLONLAR]
        secim, tamam = QInputDialog.getItem(
            self,
            "Kanalları elle ekle",
            "RTSP yol şablonu:",
            etiketler,
            0,
            False,
        )
        if not tamam:
            return
        indeks = etiketler.index(secim)
        adet, tamam = QInputDialog.getInt(
            self, "Kanalları elle ekle", "Kanal sayısı:", 4, 1, 64, 1
        )
        if not tamam:
            return
        kanallar = kanallari_uret(
            ip,
            int(cihaz.get("port") or 554),
            str(cihaz.get("username") or ""),
            str(cihaz.get("password") or ""),
            SABLONLAR[indeks][0],
            adet,
            str(cihaz.get("name") or ip),
        )
        if not kanallar:
            return
        yazilan = self._kanallari_yaz(cihaz, str(cihaz.get("id") or ""), kanallar)
        QMessageBox.information(
            self,
            "Cihaz",
            f"{len(yazilan)} kanal oluşturuldu.\n"
            "Görüntü gelmezse şablonu değiştirip tekrar deneyin.",
        )

    def _bagli_hucreleri_guncelle(self, kamera: dict) -> None:
        kid = kamera.get("id")
        for i, hucre in enumerate(self._izgara.widgets()):
            mevcut = hucre.camera
            if mevcut and mevcut.get("id") == kid:
                self._izgara.assign_camera(i, kamera)

    def _liste_menu(self, pos) -> None:
        oge = self._liste.itemAt(pos)
        menu = QMenu(self)
        if oge is None:
            ekle = menu.addAction("Cihaz Ekle…")
            secim = menu.exec(self._liste.mapToGlobal(pos))
            if secim == ekle:
                self._cihaz_ekle()
            return
        kamera = oge.data(Qt.ItemDataRole.UserRole) or {}
        ata = menu.addAction("Izgara hücresine bağla\tCtrl+Return")
        duzenle = menu.addAction("Düzenle…\tShift+F2")
        sil = menu.addAction("Listeden sil\tShift+Del")
        secim = menu.exec(self._liste.mapToGlobal(pos))
        if secim == ata:
            self._liste_cift_tik(oge)
        elif secim == duzenle:
            self._kamera_dialog(kamera)
        elif secim == sil:
            self._kamerayi_sil(kamera)

    def _kamerayi_sil(self, kamera: dict) -> None:
        """Kamerayı listeden ve bağlı olduğu hücreden kaldırır."""
        kid = str(kamera.get("id") or "")
        if not kid:
            return
        self._config.remove_camera(kid)
        for i, hucre in enumerate(self._izgara.widgets()):
            mevcut = hucre.camera
            if mevcut and mevcut.get("id") == kid:
                self._izgara.assign_camera(i, None)
        self._listeyi_yenile()
        self._slotlari_kaydet()

    def closeEvent(self, event) -> None:
        self._slotlari_kaydet()
        self._scanner.cancel()
        self._scan_thread.quit()
        self._scan_thread.wait(8000)
        self._izgara.stop_all()
        super().closeEvent(event)
