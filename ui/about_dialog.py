"""Hakkında penceresi — logo, yazar ve telif."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from app_info import (
    APP_COPYRIGHT,
    APP_CREDIT,
    APP_DISPLAY_NAME,
    APP_VERSION,
    logo_pixmap,
    uygulama_ikonu,
)


_STIL = """
QDialog { background-color: #1a1d23; }
QLabel#appName {
    color: #e8edf5;
    font-size: 20px;
    font-weight: 700;
}
QLabel#version { color: #8b95a8; font-size: 12px; }
QLabel#credit { color: #c5cdd8; font-size: 13px; }
QLabel#copy { color: #8b95a8; font-size: 11px; }
QPushButton#primary {
    background-color: #2b7fc4;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 22px;
    font-weight: 600;
}
QPushButton#primary:hover { background-color: #3d9cf0; }
"""


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Hakkında")
        self.setWindowIcon(uygulama_ikonu())
        self.setModal(True)
        self.setFixedSize(380, 360)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(28, 24, 28, 20)
        kok.setSpacing(10)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = logo_pixmap(96, self.devicePixelRatioF())
        if not pm.isNull():
            logo.setPixmap(pm)
        kok.addWidget(logo)

        ad = QLabel(APP_DISPLAY_NAME)
        ad.setObjectName("appName")
        ad.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kok.addWidget(ad)

        surum = QLabel(f"Sürüm {APP_VERSION}")
        surum.setObjectName("version")
        surum.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kok.addWidget(surum)

        kredi = QLabel(APP_CREDIT)
        kredi.setObjectName("credit")
        kredi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kredi.setWordWrap(True)
        kok.addWidget(kredi)

        telif = QLabel(APP_COPYRIGHT)
        telif.setObjectName("copy")
        telif.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kok.addWidget(telif)

        kok.addStretch(1)

        kapat = QPushButton("Tamam")
        kapat.setObjectName("primary")
        kapat.setDefault(True)
        kapat.clicked.connect(self.accept)
        kok.addWidget(kapat, alignment=Qt.AlignmentFlag.AlignCenter)
