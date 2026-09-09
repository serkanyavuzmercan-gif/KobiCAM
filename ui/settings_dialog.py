"""
Kalıcı ayarlar penceresi.

Varsayılan ızgara, kayıt klasörü, anlık görüntü formatı ve akış tercihleri.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, uygulama_ikonu
from config_manager import ConfigManager


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
QDialogButtonBox QPushButton {
    min-width: 72px;
}
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
        self.setMinimumWidth(520)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(24, 20, 24, 16)
        kok.setSpacing(14)

        form_kutu = QWidget()
        form = QFormLayout(form_kutu)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

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
        kok.addWidget(form_kutu)

        dugmeler = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        dugmeler.accepted.connect(self._kaydet)
        dugmeler.rejected.connect(self.reject)
        kok.addWidget(dugmeler)

    def _klasor_satiri(self, alan: QLineEdit, baslik: str) -> QWidget:
        """Yol kutusu + Gözat + Aç düğmelerinden oluşan satır."""
        satir = QWidget()
        yerlesim = QHBoxLayout(satir)
        yerlesim.setContentsMargins(0, 0, 0, 0)
        gozat = QPushButton("Gözat…")
        gozat.clicked.connect(lambda: self._klasor_sec(alan, baslik))
        ac = QPushButton("Aç")
        ac.setToolTip("Klasörü Windows Gezgini'nde aç")
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

    def _kaydet(self) -> None:
        self._config.set("grid_layout", int(self._izgara.currentData()), kaydet=False)
        self._config.set("record_folder", self._klasor.text().strip(), kaydet=False)
        self._config.set("snapshot_folder", self._snap_klasor.text().strip(), kaydet=False)
        self._config.set("snapshot_format", str(self._snap.currentData()), kaydet=False)
        self._config.set("record_format", str(self._kayit.currentData()), kaydet=False)
        self._config.set_display_quality(str(self._kalite.currentData() or "low"), kaydet=False)
        self._config.set("main_stream_on_zoom", self._zoom_main.isChecked(), kaydet=False)
        self._config.save()
        self.accept()
