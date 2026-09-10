"""Uzak izleme: portal adresi ve isteğe bağlı QR kod."""

from __future__ import annotations

from io import BytesIO

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, uygulama_ikonu


_STIL = """
QDialog { background-color: #1a1d23; }
QLabel#baslik { color: #e8edf5; font-size: 16px; font-weight: 700; }
QLabel#adres { color: #3d9cf0; font-size: 14px; font-weight: 600; }
QLabel#not { color: #c5cdd8; font-size: 12px; }
QPushButton#primary {
    background-color: #2b7fc4;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 18px;
    font-weight: 600;
}
QPushButton#primary:hover { background-color: #3d9cf0; }
QPushButton#ghost {
    background: transparent;
    color: #8b95a8;
    border: 1px solid #2e3440;
    border-radius: 4px;
    padding: 8px 18px;
}
"""


def _qr_pixmap(url: str, kenar: int = 220) -> QPixmap | None:
    try:
        import qrcode
    except ImportError:
        return None
    try:
        qr = qrcode.QRCode(border=2, box_size=6)
        qr.add_data(url)
        qr.make(fit=True)
        buf = BytesIO()
        try:
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(buf, format="PNG")
        except Exception:
            from qrcode.image.pure import PyPNGImage

            img = qr.make_image(image_factory=PyPNGImage)
            img.save(buf)
        pm = QPixmap()
        if not pm.loadFromData(buf.getvalue()):
            return None
        return pm.scaled(
            kenar,
            kenar,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception:
        return None


class WebPortalDialog(QDialog):
    """Telefon / tarayıcı ile izleme adresi."""

    def __init__(
        self,
        url: str = "",
        acik: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Uzak izleme")
        self.setWindowIcon(uygulama_ikonu())
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(24, 20, 24, 16)
        kok.setSpacing(12)

        baslik = QLabel("Uzak izleme")
        baslik.setObjectName("baslik")
        kok.addWidget(baslik)

        if not acik or not (url or "").strip():
            notu = QLabel(
                "Yayın kapalı. Ayarlar → Web / mobil’de «Yayını başlat» kutusunu "
                "işaretleyip Kaydet’e basın. Uzaktan izlemek için PC ve telefonda "
                "Tailscale açık ve aynı hesapta olmalıdır."
            )
            notu.setObjectName("not")
            notu.setWordWrap(True)
            kok.addWidget(notu)
        else:
            adres = (url or "").strip()
            self._url = adres
            etiket = QLabel(adres)
            etiket.setObjectName("adres")
            etiket.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            etiket.setWordWrap(True)
            kok.addWidget(etiket)
            from utils.network_helper import tailscale_adresi_mi

            uzak = tailscale_adresi_mi(adres)
            if uzak:
                aciklama_metin = (
                    "Bu adres Tailscale ağı üzerindedir; farklı Wi-Fi ve hücresel veride "
                    "de çalışır. Telefonunuzda Tailscale açık olsun. Giriş, KobiCAM "
                    "kullanıcı adı ve şifrenizledir."
                )
            else:
                aciklama_metin = (
                    "Bu adres aynı Wi-Fi içindir. Uzaktan izlemek için PC ve telefona "
                    "Tailscale kurup aynı hesapla giriş yapın; Ayarlar’da Tailscale "
                    "durumu yeşil olunca Portal adresini kullanın."
                )
            aciklama = QLabel(aciklama_metin)
            aciklama.setObjectName("not")
            aciklama.setWordWrap(True)
            kok.addWidget(aciklama)
            qr = _qr_pixmap(adres)
            if qr is not None and not qr.isNull():
                resim = QLabel()
                resim.setAlignment(Qt.AlignmentFlag.AlignCenter)
                resim.setPixmap(qr)
                kok.addWidget(resim, 0, Qt.AlignmentFlag.AlignHCenter)

        dugmeler = QHBoxLayout()
        dugmeler.addStretch(1)
        if acik and (url or "").strip():
            kopya = QPushButton("Adresi kopyala")
            kopya.setObjectName("primary")
            kopya.clicked.connect(self._kopyala)
            dugmeler.addWidget(kopya)
        kapat = QPushButton("Kapat")
        kapat.setObjectName("ghost")
        kapat.clicked.connect(self.accept)
        dugmeler.addWidget(kapat)
        kok.addLayout(dugmeler)

    def _kopyala(self) -> None:
        QApplication.clipboard().setText(getattr(self, "_url", ""))
