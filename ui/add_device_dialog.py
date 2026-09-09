"""
DVR / NVR / IP cihazı ekleme penceresi.

RTSP adresi istenmez; IP + cihaz kullanıcı/şifre ile kanallar okunur.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, uygulama_ikonu


_STIL = """
QDialog { background-color: #1a1d23; }
QLabel { color: #c5cdd8; font-size: 12px; }
QLineEdit, QComboBox {
    background-color: #12151a;
    color: #e8edf5;
    border: 1px solid #2e3440;
    border-radius: 4px;
    padding: 6px 8px;
    min-height: 18px;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #3d9cf0; }
QComboBox QAbstractItemView {
    background-color: #12151a;
    color: #e8edf5;
    selection-background-color: #2b7fc4;
}
QPushButton#primary {
    background-color: #2b7fc4;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton#primary:hover { background-color: #3d9cf0; }
QPushButton#ghost {
    background-color: transparent;
    color: #8b95a8;
    border: 1px solid #2e3440;
    border-radius: 4px;
    padding: 8px 16px;
}
"""


class AddDeviceDialog(QDialog):
    """Kayıt cihazı veya IP kamera kimliği."""

    def __init__(self, cihaz: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kaynak = dict(cihaz or {})
        self.sonuc: dict | None = None

        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Cihaz Ekle")
        self.setWindowIcon(uygulama_ikonu())
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(24, 20, 24, 16)
        kok.setSpacing(12)

        form_kutu = QWidget()
        form = QFormLayout(form_kutu)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._ad = QLineEdit()
        self._ad.setPlaceholderText("Örn. Depo NVR")
        self._ip = QLineEdit()
        self._ip.setPlaceholderText("192.168.1.64")
        self._onvif = QLineEdit()
        self._onvif.setText(str(self._kaynak.get("onvif_port") or 80))
        self._onvif.setToolTip("Cihazın HTTP / ONVIF portu (XM cihazlarda genelde 8899)")
        self._rtsp = QLineEdit()
        self._rtsp.setText(str(self._kaynak.get("port") or 554))
        self._rtsp.setToolTip("Yayın portu, genelde 554")
        self._media = QLineEdit()
        self._media.setText(str(self._kaynak.get("media_port") or 34567))
        self._media.setToolTip(
            "Cihaz menüsündeki Media Port. 34567 ise cihaz XM/Xiongmai tabanlıdır."
        )
        self._kullanici = QLineEdit()
        self._sifre = QLineEdit()
        self._sifre.setEchoMode(QLineEdit.EchoMode.Password)
        self._uretici = QComboBox()
        self._uretici.addItem("Otomatik (porta göre bul)", "auto")
        self._uretici.addItem("XM / Xiongmai (Media Port 34567)", "xm")
        self._uretici.addItem("Hikvision", "hikvision")
        self._uretici.addItem("Dahua", "dahua")
        self._uretici.addItem("Uniview", "uniview")
        self._uretici.addItem("TVT / Provision", "tvt")

        form.addRow("Ad", self._ad)
        form.addRow("Cihaz IP", self._ip)
        form.addRow("HTTP / ONVIF port", self._onvif)
        form.addRow("RTSP port", self._rtsp)
        form.addRow("Media port", self._media)
        form.addRow("Kullanıcı", self._kullanici)
        form.addRow("Şifre", self._sifre)
        form.addRow("Üretici", self._uretici)
        kok.addWidget(form_kutu)

        ipucu = QLabel(
            "KobiCAM şifresi değil, kayıt cihazının (DVR/NVR) kendi kullanıcı ve şifresini girin. "
            "Portları cihazın Ağ Ayarı ekranından okuyabilirsiniz; Media Port 34567 ise "
            "üreticiyi XM / Xiongmai seçmek bağlanmayı hızlandırır. "
            "Bağlandıktan sonra kameralar sol listedeki Kameralar bölümünde görünür."
        )
        ipucu.setWordWrap(True)
        ipucu.setStyleSheet("color: #8b95a8; font-size: 11px;")
        kok.addWidget(ipucu)

        self._ad.setText(str(self._kaynak.get("name") or ""))
        self._ip.setText(str(self._kaynak.get("ip") or ""))
        self._kullanici.setText(str(self._kaynak.get("username") or ""))
        self._sifre.setText(str(self._kaynak.get("password") or ""))
        uretici = str(self._kaynak.get("vendor") or "auto")
        idx = self._uretici.findData(uretici)
        if idx >= 0:
            self._uretici.setCurrentIndex(idx)

        dugmeler = QHBoxLayout()
        dugmeler.addStretch(1)
        iptal = QPushButton("İptal")
        iptal.setObjectName("ghost")
        iptal.clicked.connect(self.reject)
        kaydet = QPushButton("Bağlan")
        kaydet.setObjectName("primary")
        kaydet.setDefault(True)
        kaydet.clicked.connect(self._kaydet)
        dugmeler.addWidget(iptal)
        dugmeler.addWidget(kaydet)
        kok.addLayout(dugmeler)

    def _kaydet(self) -> None:
        ip = self._ip.text().strip()
        if not ip:
            QMessageBox.warning(self, "Cihaz", "Cihaz IP adresi zorunludur.")
            return
        kullanici = self._kullanici.text().strip()
        if not kullanici:
            QMessageBox.warning(self, "Cihaz", "Cihaz kullanıcı adı zorunludur.")
            return
        if not self._sifre.text():
            QMessageBox.warning(self, "Cihaz", "Cihaz şifresi zorunludur.")
            return
        try:
            onvif_port = int(self._onvif.text().strip() or "80")
            rtsp_port = int(self._rtsp.text().strip() or "554")
            media_port = int(self._media.text().strip() or "0")
        except ValueError:
            QMessageBox.warning(self, "Cihaz", "Port sayı olmalıdır.")
            return

        self.sonuc = {
            **self._kaynak,
            "name": self._ad.text().strip() or ip,
            "ip": ip,
            "onvif_port": onvif_port,
            "port": rtsp_port,
            "media_port": media_port,
            "username": kullanici,
            "password": self._sifre.text(),
            "vendor": str(self._uretici.currentData() or "auto"),
            "source": self._kaynak.get("source") or "manual",
        }
        self.accept()
