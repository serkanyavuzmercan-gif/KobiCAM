"""
Giriş ekranı ve ilk kurulum sihirbazı.

SetupWizardDialog  — Clean Installation: ana hesap oluşturma
LoginDialog        — Sonraki açılışlarda kimlik doğrulama
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, logo_pixmap, uygulama_ikonu
from auth_manager import ADMIN_USERNAME, AuthError, AuthManager


# VMS tarzı koyu, sade arayüz
_STIL = """
QDialog {
    background-color: #1a1d23;
}
QLabel#title {
    color: #e8edf5;
    font-size: 22px;
    font-weight: 700;
}
QLabel#subtitle {
    color: #8b95a8;
    font-size: 12px;
}
QLabel#brand {
    color: #3d9cf0;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 2px;
}
QLabel {
    color: #c5cdd8;
    font-size: 12px;
}
QLineEdit {
    background-color: #12151a;
    color: #e8edf5;
    border: 1px solid #2e3440;
    border-radius: 4px;
    padding: 8px 10px;
    selection-background-color: #3d9cf0;
    min-height: 20px;
}
QLineEdit:focus {
    border: 1px solid #3d9cf0;
}
QPushButton#primary {
    background-color: #2b7fc4;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 9px 18px;
    font-weight: 600;
    min-height: 22px;
}
QPushButton#primary:hover {
    background-color: #3d9cf0;
}
QPushButton#primary:pressed {
    background-color: #246aa3;
}
QPushButton#ghost {
    background-color: transparent;
    color: #8b95a8;
    border: 1px solid #2e3440;
    border-radius: 4px;
    padding: 9px 18px;
}
QPushButton#ghost:hover {
    color: #e8edf5;
    border-color: #8b95a8;
}
"""


def _baslik_blogu(alt_baslik: str) -> QWidget:
    """Ortak logo + marka + başlık bloğunu üretir."""
    kutu = QWidget()
    yerlesim = QVBoxLayout(kutu)
    yerlesim.setContentsMargins(0, 0, 0, 0)
    yerlesim.setSpacing(4)

    logo = QLabel()
    logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pm = logo_pixmap(72)
    if not pm.isNull():
        logo.setPixmap(pm)
    yerlesim.addWidget(logo)

    marka = QLabel(APP_DISPLAY_NAME.upper())
    marka.setObjectName("brand")
    marka.setAlignment(Qt.AlignmentFlag.AlignCenter)

    baslik = QLabel("Kamera İzleme Yazılımı")
    baslik.setObjectName("title")
    baslik.setAlignment(Qt.AlignmentFlag.AlignCenter)

    aciklama = QLabel(alt_baslik)
    aciklama.setObjectName("subtitle")
    aciklama.setAlignment(Qt.AlignmentFlag.AlignCenter)
    aciklama.setWordWrap(True)

    yerlesim.addWidget(marka)
    yerlesim.addWidget(baslik)
    yerlesim.addWidget(aciklama)
    return kutu


class SetupWizardDialog(QDialog):
    """İlk çalıştırmada ana hesap oluşturan kurulum sihirbazı."""

    def __init__(self, auth: AuthManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auth = auth
        self.authenticated_user: str | None = None

        self.setWindowTitle(f"{APP_DISPLAY_NAME} — İlk Kurulum")
        self.setWindowIcon(uygulama_ikonu())
        self.setModal(True)
        self.setFixedSize(420, 520)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(32, 28, 32, 24)
        kok.setSpacing(18)

        kok.addWidget(
            _baslik_blogu(
                "Sistem ilk kez çalışıyor. Ana hesap için kullanıcı adı ve şifre belirleyin."
            )
        )

        form_kutu = QWidget()
        form = QFormLayout(form_kutu)
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._kullanici = QLineEdit()
        self._kullanici.setPlaceholderText("ör. operator1")
        self._kullanici.setMaxLength(32)

        self._sifre = QLineEdit()
        self._sifre.setEchoMode(QLineEdit.EchoMode.Password)
        self._sifre.setPlaceholderText("En az 8 karakter")

        self._sifre_tekrar = QLineEdit()
        self._sifre_tekrar.setEchoMode(QLineEdit.EchoMode.Password)
        self._sifre_tekrar.setPlaceholderText("Şifreyi tekrar girin")
        self._sifre_tekrar.returnPressed.connect(self._hesap_olustur)

        form.addRow("Kullanıcı adı", self._kullanici)
        form.addRow("Şifre", self._sifre)
        form.addRow("Şifre (tekrar)", self._sifre_tekrar)
        kok.addWidget(form_kutu)

        not_label = QLabel(
            f"Yedek '{ADMIN_USERNAME}' hesabı sistemde sabittir ve buradan değiştirilemez."
        )
        not_label.setObjectName("subtitle")
        not_label.setWordWrap(True)
        kok.addWidget(not_label)

        kok.addStretch(1)

        dugmeler = QHBoxLayout()
        dugmeler.addStretch(1)
        iptal = QPushButton("İptal")
        iptal.setObjectName("ghost")
        iptal.clicked.connect(self.reject)

        olustur = QPushButton("Hesabı Oluştur")
        olustur.setObjectName("primary")
        olustur.setDefault(True)
        olustur.clicked.connect(self._hesap_olustur)

        dugmeler.addWidget(iptal)
        dugmeler.addWidget(olustur)
        kok.addLayout(dugmeler)

        self._kullanici.setFocus()

    def _hesap_olustur(self) -> None:
        """Formu doğrular ve ana hesabı kaydeder."""
        ad = self._kullanici.text()
        sifre = self._sifre.text()
        tekrar = self._sifre_tekrar.text()

        if sifre != tekrar:
            QMessageBox.warning(self, "Doğrulama", "Şifreler eşleşmiyor.")
            self._sifre_tekrar.setFocus()
            return

        try:
            kayitli = self._auth.create_user(ad, sifre)
        except AuthError as hata:
            QMessageBox.warning(self, "Kurulum", str(hata))
            return

        self.authenticated_user = kayitli
        self.accept()


class LoginDialog(QDialog):
    """Sonraki açılışlarda gösterilen giriş ekranı."""

    def __init__(self, auth: AuthManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auth = auth
        self.authenticated_user: str | None = None

        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Giriş")
        self.setWindowIcon(uygulama_ikonu())
        self.setModal(True)
        self.setFixedSize(400, 440)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(32, 28, 32, 24)
        kok.setSpacing(18)

        kok.addWidget(_baslik_blogu("Devam etmek için hesabınızla oturum açın."))

        form_kutu = QWidget()
        form = QFormLayout(form_kutu)
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._kullanici = QLineEdit()
        self._kullanici.setPlaceholderText("Kullanıcı adı")
        self._kullanici.setMaxLength(32)

        self._sifre = QLineEdit()
        self._sifre.setEchoMode(QLineEdit.EchoMode.Password)
        self._sifre.setPlaceholderText("Şifre")
        self._sifre.returnPressed.connect(self._giris_yap)

        form.addRow("Kullanıcı adı", self._kullanici)
        form.addRow("Şifre", self._sifre)
        kok.addWidget(form_kutu)

        kok.addStretch(1)

        dugmeler = QHBoxLayout()
        dugmeler.addStretch(1)

        iptal = QPushButton("Çıkış")
        iptal.setObjectName("ghost")
        iptal.clicked.connect(self.reject)

        giris = QPushButton("Giriş Yap")
        giris.setObjectName("primary")
        giris.setDefault(True)
        giris.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        giris.clicked.connect(self._giris_yap)

        dugmeler.addWidget(iptal)
        dugmeler.addWidget(giris)
        kok.addLayout(dugmeler)

        self._kullanici.setFocus()

    def _giris_yap(self) -> None:
        """Kimlik bilgilerini AuthManager ile doğrular."""
        try:
            kullanici = self._auth.authenticate(
                self._kullanici.text(),
                self._sifre.text(),
            )
        except AuthError as hata:
            QMessageBox.warning(self, "Giriş başarısız", str(hata))
            self._sifre.clear()
            self._sifre.setFocus()
            return

        self.authenticated_user = kullanici
        self.accept()
