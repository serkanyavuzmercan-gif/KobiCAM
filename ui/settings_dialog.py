"""
Kalıcı ayarlar penceresi.

Genel, Bulut, analitik ve web portal sekmeleri.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, uygulama_ikonu
from config_manager import ConfigManager


class _OAuthIsci(QThread):
    bitti = pyqtSignal(str)

    def __init__(self, cid: str, csec: str) -> None:
        super().__init__()
        self._cid = cid
        self._csec = csec

    def run(self) -> None:
        try:
            from gdrive_sync import oauth_calistir

            oauth_calistir(self._cid, self._csec)
            self.bitti.emit("")
        except Exception as hata:
            self.bitti.emit(str(hata))


_STIL = """
QDialog { background-color: #1a1d23; }
QLabel { color: #c5cdd8; font-size: 12px; }
QLineEdit, QComboBox, QSpinBox, QListWidget {
    background-color: #12151a;
    color: #e8edf5;
    border: 1px solid #2e3440;
    border-radius: 4px;
    padding: 6px 8px;
    min-height: 18px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #3d9cf0; }
QComboBox QAbstractItemView {
    background-color: #12151a;
    color: #e8edf5;
    selection-background-color: #2b7fc4;
}
QCheckBox { color: #c5cdd8; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QPushButton {
    background-color: #1a1d23;
    color: #c5cdd8;
    border: 1px solid #2e3440;
    border-radius: 4px;
    padding: 6px 12px;
}
QPushButton:hover { border-color: #3d9cf0; color: #e8edf5; }
QPushButton:disabled { color: #5a6270; border-color: #2e3440; }
QDialogButtonBox QPushButton { min-width: 72px; }
QTabWidget::pane { border: 1px solid #2e3440; }
QTabBar::tab {
    background: #12151a;
    color: #c5cdd8;
    padding: 8px 14px;
    border: 1px solid #2e3440;
}
QTabBar::tab:selected { background: #2b7fc4; color: #ffffff; }
QGroupBox {
    color: #e8edf5;
    border: 1px solid #2e3440;
    border-radius: 4px;
    margin-top: 10px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
"""


class SettingsDialog(QDialog):
    """Uygulama ayarları."""

    def __init__(
        self,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Ayarlar")
        self.setWindowIcon(uygulama_ikonu())
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(16, 16, 16, 12)
        sekmeler = QTabWidget()
        sekmeler.addTab(self._sekme_genel(), "Genel")
        sekmeler.addTab(self._sekme_drive(), "Bulut")
        sekmeler.addTab(self._sekme_analitik(), "Analitik")
        sekmeler.addTab(self._sekme_web(), "Web / mobil")
        sekmeler.addTab(self._sekme_sunucu(), "Sunucu Bağlantı Durumu")
        kok.addWidget(sekmeler, 1)

        dugmeler = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        dugmeler.button(QDialogButtonBox.StandardButton.Ok).setText("Kaydet")
        dugmeler.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        dugmeler.accepted.connect(self._kaydet)
        dugmeler.rejected.connect(self.reject)
        kok.addWidget(dugmeler)
        self._an_timer = QTimer(self)
        self._an_timer.timeout.connect(self._canli_analitik_yenile)
        self._an_timer.timeout.connect(self._tailscale_yenile)
        self._an_timer.timeout.connect(self._sunucu_durum_yenile)
        self._an_timer.start(2000)
        self._canli_analitik_yenile()
        self._tailscale_yenile()
        self._sunucu_durum_yenile()

    def _sekme_genel(self) -> QWidget:
        kutu = QWidget()
        form = QFormLayout(kutu)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        config = self._config

        self._izgara = QComboBox()
        for sayi, etiket in ((1, "1'li"), (4, "4'lü"), (9, "9'lu"), (16, "16'lı")):
            self._izgara.addItem(etiket, sayi)
        mevcut = int(config.get("grid_layout", 4) or 4)
        idx = self._izgara.findData(mevcut)
        if idx >= 0:
            self._izgara.setCurrentIndex(idx)

        self._klasor = QLineEdit()
        self._klasor.setPlaceholderText(str(ConfigManager.varsayilan_klasor()))
        self._klasor.setText(str(config.get("record_folder") or ""))
        klasor_satir = self._klasor_satiri(self._klasor, "Video kayıt klasörü")

        self._snap_klasor = QLineEdit()
        self._snap_klasor.setPlaceholderText("Boş bırakılırsa video kayıt klasörü kullanılır")
        self._snap_klasor.setText(str(config.get("snapshot_folder") or ""))
        snap_klasor_satir = self._klasor_satiri(self._snap_klasor, "Anlık görüntü klasörü")

        self._snap = QComboBox()
        self._snap.addItem("PNG", "png")
        self._snap.addItem("JPEG", "jpg")
        snap = str(config.get("snapshot_format") or "png").lower()
        self._snap.setCurrentIndex(1 if snap in ("jpg", "jpeg") else 0)

        self._kayit = QComboBox()
        self._kayit.addItem("MP4 (görüntü kopya, ses AAC)", "mp4")
        self._kayit.addItem("MKV (görüntü ve ses kopya)", "mkv")
        kayit = str(config.get("record_format") or "mp4").lower()
        self._kayit.setCurrentIndex(1 if kayit == "mkv" else 0)

        self._kalite = QComboBox()
        self._kalite.addItem("Düşük — sub-stream (az bant / CPU)", "low")
        self._kalite.addItem("Yüksek — main-stream (tam çözünürlük)", "high")
        kalite = config.display_quality()
        k_idx = self._kalite.findData(kalite)
        self._kalite.setCurrentIndex(k_idx if k_idx >= 0 else 0)

        self._zoom_main = QCheckBox("Düşük kalitedeyken tekli görünüm / dijital zoom'da HD'ye geç")
        self._zoom_main.setChecked(bool(config.get("main_stream_on_zoom", True)))

        form.addRow("Varsayılan ızgara", self._izgara)
        form.addRow("Video kayıtları", klasor_satir)
        form.addRow("Anlık görüntüler", snap_klasor_satir)
        form.addRow("Anlık görüntü biçimi", self._snap)
        form.addRow("Kayıt formatı", self._kayit)
        form.addRow("Açılış görüntü kalitesi", self._kalite)
        form.addRow("", self._zoom_main)
        return kutu

    def _sekme_drive(self) -> QWidget:
        kutu = QWidget()
        form = QFormLayout(kutu)
        form.setSpacing(8)
        cfg = self._config
        self._gdrive_acik = QCheckBox("Google Drive senkronunu aç")
        self._gdrive_acik.setChecked(bool(cfg.get("gdrive_enabled")))
        self._gdrive_klasor = QLineEdit(str(cfg.get("gdrive_folder_name") or "KobiCAM_Cloud"))
        self._gdrive_saat = QSpinBox()
        self._gdrive_saat.setRange(24, 24 * 30)
        self._gdrive_saat.setValue(int(cfg.get("gdrive_retention_hours") or 120))
        self._gdrive_seg = QSpinBox()
        self._gdrive_seg.setRange(60, 3600)
        self._gdrive_seg.setSuffix(" sn")
        self._gdrive_seg.setValue(int(cfg.get("gdrive_segment_seconds") or 300))
        self._gdrive_sil = QCheckBox("Yüklendikten sonra yerel segmenti sil")
        self._gdrive_sil.setChecked(bool(cfg.get("gdrive_delete_local", True)))
        self._gdrive_cid = QLineEdit(str(cfg.get("gdrive_oauth_client_id") or ""))
        self._gdrive_csec = QLineEdit(str(cfg.get("gdrive_oauth_client_secret") or ""))
        self._gdrive_csec.setEchoMode(QLineEdit.EchoMode.Password)
        self._gdrive_kameralar = QListWidget()
        self._gdrive_kameralar.setMaximumHeight(140)
        secili = set(str(x) for x in (cfg.get("gdrive_camera_ids") or []))
        for kam in cfg.cameras():
            kid = str(kam.get("id") or "")
            if not kid:
                continue
            oge = QListWidgetItem(str(kam.get("name") or kid))
            oge.setData(Qt.ItemDataRole.UserRole, kid)
            oge.setFlags(oge.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            oge.setCheckState(
                Qt.CheckState.Checked if kid in secili else Qt.CheckState.Unchecked
            )
            self._gdrive_kameralar.addItem(oge)
        self._gdrive_baglan = QPushButton("Google hesabına bağlan…")
        self._gdrive_baglan.clicked.connect(self._gdrive_oauth)
        form.addRow(self._gdrive_acik)
        form.addRow("Drive klasör adı", self._gdrive_klasor)
        form.addRow("Saklama süresi (saat)", self._gdrive_saat)
        form.addRow("Segment süresi", self._gdrive_seg)
        form.addRow(self._gdrive_sil)
        form.addRow("OAuth Client ID", self._gdrive_cid)
        form.addRow("OAuth Client secret", self._gdrive_csec)
        form.addRow("Senkron kameralar", self._gdrive_kameralar)
        form.addRow(self._gdrive_baglan)
        ipucu = QLabel(
            "1. Google Drive hesabınızı bağlayın.\n"
            "2. Otomatik senkronizasyonu açın.\n"
            "3. Sistem 5 günden eski videoları otomatik siler, harddiskiniz dolmaz."
        )
        ipucu.setWordWrap(True)
        form.addRow(ipucu)
        return kutu

    def _sekme_analitik(self) -> QWidget:
        kutu = QWidget()
        form = QFormLayout(kutu)
        cfg = self._config
        self._an_acik = QCheckBox("İnsan sayımı / kalma süresi analitiğini aç")
        self._an_acik.setChecked(bool(cfg.get("analytics_enabled")))
        self._an_kamera = QComboBox()
        self._an_kamera.addItem("(seçilmedi)", "")
        hedef = str(cfg.get("analytics_camera_id") or "")
        for kam in cfg.cameras():
            kid = str(kam.get("id") or "")
            self._an_kamera.addItem(str(kam.get("name") or kid), kid)
        idx = self._an_kamera.findData(hedef)
        if idx >= 0:
            self._an_kamera.setCurrentIndex(idx)
        self._an_fps = QSpinBox()
        self._an_fps.setRange(1, 15)
        self._an_fps.setValue(int(cfg.get("analytics_fps") or 5))
        form.addRow(self._an_acik)
        form.addRow("Analiz kamerası", self._an_kamera)
        form.addRow("İşleme FPS", self._an_fps)
        panel = QGroupBox("Canlı durum")
        panel_y = QVBoxLayout(panel)
        self._an_durum = QLabel("Durduruldu")
        self._an_ozet = QLabel("Giren insan: 0 | Çıkan insan: 0 | Ort. kalma süresi: 0 dk")
        self._an_yuk = QLabel("YOLOv8n (CPU) — %0 kare işleniyor")
        for et in (self._an_durum, self._an_ozet, self._an_yuk):
            et.setWordWrap(True)
            panel_y.addWidget(et)
        form.addRow(panel)
        ipucu = QLabel(
            "Sayım çizgisini Analitik menüsünden açılan pencerede kare üzerine iki tıklayarak çizin."
        )
        ipucu.setWordWrap(True)
        form.addRow(ipucu)
        return kutu

    def _canli_analitik_yenile(self) -> None:
        if not hasattr(self, "_an_durum"):
            return
        parent = self.parent()
        isci = getattr(parent, "_an_isci", None)
        calisiyor = isci is not None and isci.isRunning()
        if calisiyor:
            self._an_durum.setText("Çalışıyor")
            self._an_durum.setStyleSheet("color: #5dca7a; font-weight: 700;")
        else:
            self._an_durum.setText("Durduruldu")
            self._an_durum.setStyleSheet("color: #e07070; font-weight: 700;")
        kid = str(self._an_kamera.currentData() or self._config.get("analytics_camera_id") or "")
        giren = cikan = 0
        ort_sn = 0.0
        if kid:
            try:
                from analytics_worker import saatlik_son_24saat

                giren, cikan, ort_sn = saatlik_son_24saat(kid)
            except Exception:
                pass
        ort_dk = ort_sn / 60.0
        self._an_ozet.setText(
            f"Giren insan: {giren} | Çıkan insan: {cikan} | Ort. kalma süresi: {ort_dk:.1f} dk"
        )
        cihaz = "CPU"
        try:
            import torch

            if torch.cuda.is_available():
                cihaz = "GPU"
        except Exception:
            pass
        fps = int(self._an_fps.value() or 5) if calisiyor else 0
        yuk = max(0, min(100, int(round((fps / 15.0) * 100)))) if calisiyor else 0
        self._an_yuk.setText(f"YOLOv8n ({cihaz}) — %{yuk} kare işleniyor")

    def _sekme_web(self) -> QWidget:
        kutu = QWidget()
        form = QFormLayout(kutu)
        cfg = self._config
        self._web_bind = QLineEdit(str(cfg.get("web_bind") or "0.0.0.0"))
        self._web_port = QSpinBox()
        self._web_port.setRange(1024, 65535)
        self._web_port.setValue(int(cfg.get("web_port") or 8765))
        self._web_max = QSpinBox()
        self._web_max.setRange(1, 4)
        self._web_max.setValue(int(cfg.get("web_max_streams") or 4))
        self._web_port.valueChanged.connect(self._tailscale_yenile)
        self._web_port.valueChanged.connect(self._sunucu_durum_yenile)
        ts_kutu = QGroupBox("Tailscale ile Güvenli Uzak Erişim")
        ts_y = QVBoxLayout(ts_kutu)
        self._ts_durum = QLabel("🔴 Tailscale Çalışmıyor")
        self._ts_durum.setWordWrap(True)
        ts_y.addWidget(self._ts_durum)
        form.addRow("Dinleme adresi", self._web_bind)
        form.addRow("Port", self._web_port)
        form.addRow("En fazla HLS yayın", self._web_max)
        form.addRow(ts_kutu)
        ipucu = QLabel(
            "Yayın, saat yanındaki KobiCAM Server Gateway uygulamasındadır. "
            "VMS’i kapatsanız da yayın kesilmez. Port ve dinleme adresi burada kaydedilir; "
            "sunucu aynı config.json dosyasını okur."
        )
        ipucu.setWordWrap(True)
        form.addRow(ipucu)
        return kutu

    def _sekme_sunucu(self) -> QWidget:
        kutu = QWidget()
        form = QFormLayout(kutu)
        self._srv_durum = QLabel("Pasif")
        self._srv_url = QLineEdit()
        self._srv_url.setReadOnly(True)
        self._srv_url.setPlaceholderText("Sunucu çalışınca dolar")
        kopya = QPushButton("Bağlantı Adresini Kopyala")
        kopya.clicked.connect(self._web_url_kopyala)
        self._srv_qr = QLabel()
        self._srv_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._srv_qr.setMinimumHeight(160)
        self._srv_qr.setText("QR kod için sunucu ve Tailscale gerekli")
        form.addRow("Sunucu yayın durumu", self._srv_durum)
        form.addRow("Tailscale adresi", self._srv_url)
        form.addRow(kopya)
        form.addRow("Mobil bağlantı QR", self._srv_qr)
        ipucu = QLabel(
            "Saat yanındaki KobiCAM Server Gateway çalışıyorsa durum Aktif olur. "
            "Telefon aynı Tailscale hesabıyla bu adresi tarayıcıya yazar."
        )
        ipucu.setWordWrap(True)
        form.addRow(ipucu)
        return kutu

    def _tailscale_yenile(self) -> None:
        if not hasattr(self, "_ts_durum"):
            return
        from utils.network_helper import get_tailscale_ip

        ip = get_tailscale_ip()
        if ip:
            self._ts_durum.setText(f"🟢 Tailscale Bağlı: {ip}")
            self._ts_durum.setStyleSheet("color: #5dca7a; font-weight: 700;")
        else:
            self._ts_durum.setText("🔴 Tailscale Çalışmıyor")
            self._ts_durum.setStyleSheet("color: #e07070; font-weight: 700;")

    def _sunucu_durum_yenile(self) -> None:
        if not hasattr(self, "_srv_durum"):
            return
        from utils.network_helper import yerel_health, portal_url

        port = int(self._web_port.value() if hasattr(self, "_web_port") else 8765)
        saglik = yerel_health(port)
        if saglik:
            self._srv_durum.setText("Aktif")
            self._srv_durum.setStyleSheet("color: #5dca7a; font-weight: 700;")
            ts = str(saglik.get("tailscale") or "")
            adres = portal_url(port) or (f"http://{ts}:{port}" if ts else f"http://127.0.0.1:{port}")
            self._srv_url.setText(adres)
            self._qr_goster(adres if ts else "")
        else:
            self._srv_durum.setText("Pasif")
            self._srv_durum.setStyleSheet("color: #e07070; font-weight: 700;")
            self._srv_url.clear()
            self._qr_goster("")

    def _qr_goster(self, url: str) -> None:
        if not hasattr(self, "_srv_qr"):
            return
        if not url:
            self._srv_qr.setPixmap(QPixmap())
            self._srv_qr.setText("QR kod için sunucu ve Tailscale gerekli")
            return
        from ui.web_portal_dialog import _qr_pixmap

        pm = _qr_pixmap(url, 180)
        if pm is not None and not pm.isNull():
            self._srv_qr.setText("")
            self._srv_qr.setPixmap(pm)
        else:
            self._srv_qr.setPixmap(QPixmap())
            self._srv_qr.setText(url)

    def _web_qr_goster(self) -> None:
        url = self._srv_url.text().strip() if hasattr(self, "_srv_url") else ""
        if not url:
            return
        from ui.web_portal_dialog import WebPortalDialog

        WebPortalDialog(url, True, self).exec()

    def _klasor_satiri(self, alan: QLineEdit, baslik: str) -> QWidget:
        satir = QWidget()
        yerlesim = QHBoxLayout(satir)
        yerlesim.setContentsMargins(0, 0, 0, 0)
        gozat = QPushButton("Gözat…")
        gozat.clicked.connect(lambda: self._klasor_sec(alan, baslik))
        ac = QPushButton("Aç")
        ac.clicked.connect(lambda: self._klasor_ac(alan))
        yerlesim.addWidget(alan, 1)
        yerlesim.addWidget(gozat)
        yerlesim.addWidget(ac)
        return satir

    def _klasor_sec(self, alan: QLineEdit, baslik: str) -> None:
        baslangic = alan.text().strip() or str(ConfigManager.varsayilan_klasor())
        secilen = QFileDialog.getExistingDirectory(self, baslik, baslangic)
        if secilen:
            alan.setText(secilen)

    def _klasor_ac(self, alan: QLineEdit) -> None:
        yol = Path(alan.text().strip() or str(ConfigManager.varsayilan_klasor()))
        yol.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(yol)))

    def _gdrive_oauth(self) -> None:
        cid = self._gdrive_cid.text().strip()
        csec = self._gdrive_csec.text().strip()
        if not cid or not csec:
            QMessageBox.warning(
                self,
                "Google Drive",
                "Önce Client ID ve secret girin, Kaydet deyip tekrar bağlanın.",
            )
            return
        self._config.set("gdrive_oauth_client_id", cid, kaydet=False)
        self._config.set("gdrive_oauth_client_secret", csec, kaydet=False)
        self._config.save()
        self._gdrive_baglan.setEnabled(False)
        self._gdrive_baglan.setText("Tarayıcı bekleniyor…")
        self._oauth_isci = _OAuthIsci(cid, csec)
        self._oauth_isci.bitti.connect(self._oauth_bitti)
        self._oauth_isci.start()

    def _oauth_bitti(self, hata: str) -> None:
        self._gdrive_baglan.setEnabled(True)
        self._gdrive_baglan.setText("Google hesabına bağlan…")
        if hata:
            QMessageBox.warning(self, "Google Drive", hata)
            return
        QMessageBox.information(self, "Google Drive", "Google hesabı bağlandı.")

    def _kaydet(self) -> None:
        self._config.set("grid_layout", int(self._izgara.currentData()), kaydet=False)
        self._config.set("record_folder", self._klasor.text().strip(), kaydet=False)
        self._config.set("snapshot_folder", self._snap_klasor.text().strip(), kaydet=False)
        self._config.set("snapshot_format", str(self._snap.currentData()), kaydet=False)
        self._config.set("record_format", str(self._kayit.currentData()), kaydet=False)
        self._config.set_display_quality(str(self._kalite.currentData() or "low"), kaydet=False)
        self._config.set("main_stream_on_zoom", self._zoom_main.isChecked(), kaydet=False)

        ids: list[str] = []
        for i in range(self._gdrive_kameralar.count()):
            oge = self._gdrive_kameralar.item(i)
            if oge and oge.checkState() == Qt.CheckState.Checked:
                ids.append(str(oge.data(Qt.ItemDataRole.UserRole) or ""))
        self._config.set("gdrive_enabled", self._gdrive_acik.isChecked(), kaydet=False)
        self._config.set("gdrive_folder_name", self._gdrive_klasor.text().strip() or "KobiCAM_Cloud", kaydet=False)
        self._config.set("gdrive_retention_hours", int(self._gdrive_saat.value()), kaydet=False)
        self._config.set("gdrive_segment_seconds", int(self._gdrive_seg.value()), kaydet=False)
        self._config.set("gdrive_delete_local", self._gdrive_sil.isChecked(), kaydet=False)
        self._config.set("gdrive_oauth_client_id", self._gdrive_cid.text().strip(), kaydet=False)
        self._config.set("gdrive_oauth_client_secret", self._gdrive_csec.text(), kaydet=False)
        self._config.set("gdrive_camera_ids", [x for x in ids if x], kaydet=False)

        self._config.set("analytics_enabled", self._an_acik.isChecked(), kaydet=False)
        self._config.set("analytics_camera_id", str(self._an_kamera.currentData() or ""), kaydet=False)
        self._config.set("analytics_fps", int(self._an_fps.value()), kaydet=False)

        self._config.set("web_bind", self._web_bind.text().strip() or "0.0.0.0", kaydet=False)
        self._config.set("web_port", int(self._web_port.value()), kaydet=False)
        self._config.set("web_max_streams", int(self._web_max.value()), kaydet=False)
        adres = self._srv_url.text().strip() if hasattr(self, "_srv_url") else ""
        if adres:
            self._config.set("web_last_url", adres, kaydet=False)
        self._config.save()
        self.accept()

    def _web_url_kopyala(self) -> None:
        metin = self._srv_url.text().strip() if hasattr(self, "_srv_url") else ""
        if not metin:
            QMessageBox.information(
                self,
                "Uzak izleme",
                "Sunucu Gateway çalışmıyor veya Tailscale adresi yok. "
                "Saat yanındaki KobiCAM Server’ı başlatın.",
            )
            return
        QApplication.clipboard().setText(metin)
        QMessageBox.information(self, "Uzak izleme", "Adres panoya kopyalandı.")
