"""
Kamera ekleme / düzenleme penceresi.

Keşif çoğu cihazda kimliksiz RTSP URI üretmez; kullanıcı burada
ad, kimlik bilgisi ve main/sub URL girer. Boş URL'ler üretici şablonundan doldurulur.
"""

from __future__ import annotations

from app_info import APP_DISPLAY_NAME, uygulama_ikonu
from urllib.parse import quote, urlparse, urlunparse

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


def rtsp_url_olustur(
    kullanici: str,
    sifre: str,
    ip: str,
    port: int,
    yol: str,
) -> str:
    """Kullanıcı/şifreyi URL içinde kaçırarak RTSP adresi üretir."""
    ip = (ip or "").strip()
    if not ip:
        return ""
    kimlik = ""
    if kullanici.strip():
        kimlik = f"{quote(kullanici.strip(), safe='')}:{quote(sifre, safe='')}@"
    yol = yol if yol.startswith("/") else f"/{yol}"
    return f"rtsp://{kimlik}{ip}:{int(port)}{yol}"


def _url_kimlik_guncelle(url: str, kullanici: str, sifre: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    ayr = urlparse(url)
    host = ayr.hostname or ""
    if not host:
        return url
    if kullanici.strip():
        netloc = f"{quote(kullanici.strip(), safe='')}:{quote(sifre, safe='')}@{host}"
    else:
        netloc = host
    if ayr.port:
        netloc += f":{ayr.port}"
    return urlunparse((ayr.scheme or "rtsp", netloc, ayr.path, ayr.params, ayr.query, ayr.fragment))


# Üretici → (main path, sub path)
_SABLONLAR = {
    "generic": ("/stream1", "/stream2"),
    "hikvision": ("/Streaming/Channels/101", "/Streaming/Channels/102"),
    "dahua": (
        "/cam/realmonitor?channel=1&subtype=0",
        "/cam/realmonitor?channel=1&subtype=1",
    ),
}


class AddCameraDialog(QDialog):
    """Yeni kamera kaydı veya mevcut kaydı düzenleme."""

    def __init__(self, kamera: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kaynak = dict(kamera or {})
        self.sonuc: dict | None = None

        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Kamera RTSP")
        self.setWindowIcon(uygulama_ikonu())
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(24, 20, 24, 16)
        kok.setSpacing(12)

        form_kutu = QWidget()
        form = QFormLayout(form_kutu)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._ad = QLineEdit()
        self._ad.setPlaceholderText("Ön kapı")
        self._ip = QLineEdit()
        self._ip.setPlaceholderText("192.168.1.64")
        self._port = QLineEdit()
        self._port.setText(str(self._kaynak.get("port") or 554))
        self._kullanici = QLineEdit()
        self._sifre = QLineEdit()
        self._sifre.setEchoMode(QLineEdit.EchoMode.Password)

        self._uretici = QComboBox()
        self._uretici.addItem("Genel", "generic")
        self._uretici.addItem("Hikvision", "hikvision")
        self._uretici.addItem("Dahua", "dahua")

        self._main = QLineEdit()
        self._main.setPlaceholderText("rtsp://kullanici:sifre@ip:554/...")
        self._sub = QLineEdit()
        self._sub.setPlaceholderText("Düşük çözünürlük (sub-stream)")

        form.addRow("Ad", self._ad)
        form.addRow("IP", self._ip)
        form.addRow("Port", self._port)
        form.addRow("Kullanıcı", self._kullanici)
        form.addRow("Şifre", self._sifre)
        form.addRow("Üretici", self._uretici)
        form.addRow("Main RTSP", self._main)
        form.addRow("Sub RTSP", self._sub)
        kok.addWidget(form_kutu)

        ipucu = QLabel(
            "Tek bir kameranın yayın adresini düzenler. DVR/NVR için Cihaz Ekle kullanın."
        )
        ipucu.setObjectName("subtitle")
        ipucu.setWordWrap(True)
        ipucu.setStyleSheet("color: #8b95a8; font-size: 11px;")
        kok.addWidget(ipucu)

        self._ad.setText(str(self._kaynak.get("name") or ""))
        self._ip.setText(str(self._kaynak.get("ip") or ""))
        self._kullanici.setText(str(self._kaynak.get("username") or ""))
        self._sifre.setText(str(self._kaynak.get("password") or ""))
        self._main.setText(str(self._kaynak.get("main_url") or ""))
        self._sub.setText(str(self._kaynak.get("sub_url") or ""))

        self._ip.textChanged.connect(self._kimlik_veya_sablon)
        self._port.textChanged.connect(self._kimlik_veya_sablon)
        self._kullanici.textChanged.connect(self._kimlik_veya_sablon)
        self._sifre.textChanged.connect(self._kimlik_veya_sablon)
        self._uretici.currentIndexChanged.connect(self._sablon_doldur)

        if not self._main.text().strip() and self._ip.text().strip():
            self._sablon_doldur()

        dugmeler = QHBoxLayout()
        dugmeler.addStretch(1)
        iptal = QPushButton("İptal")
        iptal.setObjectName("ghost")
        iptal.clicked.connect(self.reject)
        kaydet = QPushButton("Kaydet")
        kaydet.setObjectName("primary")
        kaydet.setDefault(True)
        kaydet.clicked.connect(self._kaydet)
        dugmeler.addWidget(iptal)
        dugmeler.addWidget(kaydet)
        kok.addLayout(dugmeler)

    def _kanal_kaydi_mi(self) -> bool:
        return bool(self._kaynak.get("channel") or self._kaynak.get("source_token"))

    def _kimlik_veya_sablon(self) -> None:
        if self._kanal_kaydi_mi() and (self._main.text().strip() or self._kaynak.get("main_url")):
            self._main.setText(
                _url_kimlik_guncelle(
                    self._main.text() or str(self._kaynak.get("main_url") or ""),
                    self._kullanici.text(),
                    self._sifre.text(),
                )
            )
            if self._sub.text().strip() or self._kaynak.get("sub_url"):
                self._sub.setText(
                    _url_kimlik_guncelle(
                        self._sub.text() or str(self._kaynak.get("sub_url") or ""),
                        self._kullanici.text(),
                        self._sifre.text(),
                    )
                )
            return
        if not self._main.text().strip() or not self._kanal_kaydi_mi():
            self._sablon_doldur()

    def _sablon_doldur(self) -> None:
        anahtar = str(self._uretici.currentData() or "generic")
        main_yol, sub_yol = _SABLONLAR[anahtar]
        ip = self._ip.text().strip()
        try:
            port = int(self._port.text().strip() or "554")
        except ValueError:
            port = 554
        kullanici = self._kullanici.text()
        sifre = self._sifre.text()
        self._main.setText(rtsp_url_olustur(kullanici, sifre, ip, port, main_yol))
        self._sub.setText(rtsp_url_olustur(kullanici, sifre, ip, port, sub_yol))

    def _kaydet(self) -> None:
        ad = self._ad.text().strip()
        ip = self._ip.text().strip()
        main = self._main.text().strip()
        if not ip:
            QMessageBox.warning(self, "Kamera", "IP adresi zorunludur.")
            return
        if not main:
            QMessageBox.warning(self, "Kamera", "Main RTSP adresi zorunludur.")
            return
        try:
            port = int(self._port.text().strip() or "554")
        except ValueError:
            QMessageBox.warning(self, "Kamera", "Port sayı olmalıdır.")
            return

        self.sonuc = {
            **self._kaynak,
            "name": ad or ip,
            "ip": ip,
            "port": port,
            "username": self._kullanici.text().strip(),
            "password": self._sifre.text(),
            "main_url": main,
            "sub_url": self._sub.text().strip(),
            "source": self._kaynak.get("source") or "manual",
        }
        self.accept()
