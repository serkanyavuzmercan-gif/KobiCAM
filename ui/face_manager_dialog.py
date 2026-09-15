"""Tanımsız yüzler ve kayıtlı kişiler: isim ver, birleştir, sil."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, uygulama_ikonu
from database import face_db
from utils.cleanup import auto_clean_unassigned_faces

_STIL = """
QDialog { background:#1a1d23; }
QLabel { color:#c5cdd8; }
QTabWidget::pane { border:1px solid #2a3140; }
QTabBar::tab { background:#12151a; color:#c5cdd8; padding:8px 16px; }
QTabBar::tab:selected { background:#2b7fc4; color:#fff; }
QPushButton { background:#243044; color:#e8edf5; border:none; padding:6px 10px; border-radius:4px; }
QPushButton:hover { background:#2b7fc4; }
"""


class FaceManagerDialog(QDialog):
    """Kişi ve yüz yönetimi."""

    galeri_degisti = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Kişi ve Yüz Yönetimi")
        self.setWindowIcon(uygulama_ikonu())
        self.resize(860, 620)
        self.setStyleSheet(_STIL)

        kok = QVBoxLayout(self)
        self._sekme = QTabWidget()
        self._tanimsiz = QScrollArea()
        self._kayitli = QScrollArea()
        for alan in (self._tanimsiz, self._kayitli):
            alan.setWidgetResizable(True)
            alan.setStyleSheet("QScrollArea { border:none; background:#12151a; }")
        self._sekme.addTab(self._tanimsiz, "Tanımsız Yüzler")
        self._sekme.addTab(self._kayitli, "Kayıtlı Kişiler")
        kok.addWidget(self._sekme, 1)
        alt = QHBoxLayout()
        benzer = QPushButton("Benzerleri birleştir")
        benzer.clicked.connect(self._benzerleri_birlestir)
        disa = QPushButton("Dışa aktar")
        disa.clicked.connect(self._disa_aktar)
        ice = QPushButton("İçe aktar")
        ice.clicked.connect(self._ice_aktar)
        yenile = QPushButton("Yenile")
        yenile.clicked.connect(self._yenile)
        alt.addWidget(benzer)
        alt.addWidget(disa)
        alt.addWidget(ice)
        alt.addStretch(1)
        alt.addWidget(yenile)
        kok.addLayout(alt)
        self._zaman = QTimer(self)
        self._zaman.timeout.connect(self._yenile)
        self._zaman.start(2500)
        self._imza = None
        self._yenile()

    def _yenile(self) -> None:
        silinen = auto_clean_unassigned_faces()
        if silinen:
            self.galeri_degisti.emit()
        tanimsiz_liste = face_db.kisiler(yalniz_bilinen=False)
        kayitli = face_db.kisiler(yalniz_bilinen=True)
        imza = (
            tuple(
                (k["id"], tuple((e.get("image_path") or "") for e in k.get("encodings") or []))
                for k in tanimsiz_liste
            ),
            tuple(k["id"] for k in kayitli),
        )
        if imza == self._imza:
            return
        onceki = None if self._imza is None else self._imza[0]
        self._imza = imza
        self._tanimsiz.setWidget(self._izgara(tanimsiz_liste, True))
        self._kayitli.setWidget(self._izgara(kayitli, False))
        if onceki is not None and imza[0] != onceki:
            self._tanimsiz.verticalScrollBar().setValue(0)

    def _izgara(self, kisiler: list[dict], tanimsiz: bool) -> QWidget:
        kutu = QWidget()
        kutu.setStyleSheet("background:#12151a;")
        ız = QGridLayout(kutu)
        ız.setSpacing(12)
        if not kisiler:
            bos = QLabel("Kayıt yok." if not tanimsiz else "Henüz tanımsız yüz yok.")
            bos.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ız.addWidget(bos, 0, 0)
            return kutu
        for i, kisi in enumerate(kisiler):
            ız.addWidget(self._kart(kisi, tanimsiz), i // 3, i % 3)
        ız.setRowStretch((len(kisiler) + 2) // 3, 1)
        return kutu

    def _kart(self, kisi: dict, tanimsiz: bool) -> QWidget:
        kart = QWidget()
        kart.setStyleSheet(
            "QWidget { background:#1a1d23; border:1px solid #2a3140; border-radius:8px; }"
        )
        yer = QVBoxLayout(kart)
        foto = QLabel()
        foto.setFixedSize(140, 140)
        foto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foto.setStyleSheet("border:none; background:#0b0d10;")
        yol = face_db.kisi_kapak_yolu(int(kisi.get("id") or 0), kisi.get("encodings") or [])
        if yol:
            pm = QPixmap(yol)
            if not pm.isNull():
                kapak = pm.scaled(
                    140,
                    140,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                ox = max(0, (kapak.width() - 140) // 2)
                oy = max(0, (kapak.height() - 140) // 2)
                foto.setPixmap(kapak.copy(ox, oy, 140, 140))
            else:
                foto.setText("Görüntü yok")
        else:
            foto.setText("Görüntü yok")
        yer.addWidget(foto, 0, Qt.AlignmentFlag.AlignHCenter)
        ad = QLabel(str(kisi.get("name") or ""))
        ad.setWordWrap(True)
        ad.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ad.setStyleSheet("border:none; font-weight:600; color:#e8edf5;")
        yer.addWidget(ad)
        pid = int(kisi["id"])
        dugmeler = QHBoxLayout()
        if tanimsiz:
            tanimla = QPushButton("Tanımla")
            tanimla.clicked.connect(lambda _=False, p=pid: self._tanimla(p))
            dugmeler.addWidget(tanimla)
        else:
            adlandir = QPushButton("Yeniden adlandır")
            adlandir.clicked.connect(lambda _=False, p=pid: self._tanimla(p))
            dugmeler.addWidget(adlandir)
        birlestir = QPushButton("Birleştir")
        birlestir.clicked.connect(lambda _=False, p=pid: self._birlestir(p))
        sil = QPushButton("Sil")
        sil.clicked.connect(lambda _=False, p=pid: self._sil(p))
        dugmeler.addWidget(birlestir)
        dugmeler.addWidget(sil)
        yer.addLayout(dugmeler)
        return kart

    def _tanimla(self, pid: int) -> None:
        kisi = face_db.kisi_al(pid)
        mevcut = str((kisi or {}).get("name") or "")
        isim, ok = QInputDialog.getText(self, "İsim ver", "Ad soyad:", text=mevcut)
        if not ok:
            return
        try:
            face_db.isim_ver(pid, isim)
        except ValueError as hata:
            QMessageBox.warning(self, "Kişi", str(hata))
            return
        self._yenile()
        self.galeri_degisti.emit()

    def _birlestir(self, pid: int) -> None:
        adaylar = [k for k in face_db.kisiler(yalniz_bilinen=True) if int(k["id"]) != pid]
        if not adaylar:
            QMessageBox.information(self, "Birleştir", "Hedef olacak kayıtlı kişi yok.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Başka kişiye ekle")
        dlg.setStyleSheet(_STIL)
        yer = QVBoxLayout(dlg)
        yer.addWidget(QLabel("Bu yüzü hangi kayıtlı kişiye ekleyelim?"))
        combo = QComboBox()
        for k in adaylar:
            combo.addItem(str(k["name"]), int(k["id"]))
        yer.addWidget(combo)
        kutular = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        kutular.accepted.connect(dlg.accept)
        kutular.rejected.connect(dlg.reject)
        yer.addWidget(kutular)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        hedef = int(combo.currentData())
        try:
            face_db.birlestir(pid, hedef)
        except ValueError as hata:
            QMessageBox.warning(self, "Birleştir", str(hata))
            return
        self._yenile()
        self.galeri_degisti.emit()

    def _sil(self, pid: int) -> None:
        kisi = face_db.kisi_al(pid)
        ad = str((kisi or {}).get("name") or pid)
        cevap = QMessageBox.question(
            self,
            "Sil",
            f"“{ad}” ve yüz fotoğrafları silinsin mi?",
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return
        face_db.kisi_sil(pid)
        self._yenile()
        self.galeri_degisti.emit()

    def _benzerleri_birlestir(self) -> None:
        n = face_db.benzerleri_birlestir(0.55)
        self._yenile()
        self.galeri_degisti.emit()
        if n:
            QMessageBox.information(self, "Birleştir", f"{n} benzer kayıt birleştirildi.")
        else:
            QMessageBox.information(self, "Birleştir", "Birleşecek kadar benzer yüz yok.")

    def _disa_aktar(self) -> None:
        from datetime import datetime

        from utils.face_transfer import disa_aktar

        oner = f"KobiCAM-yuzler-{datetime.now().strftime('%Y%m%d')}.zip"
        yol, _ = QFileDialog.getSaveFileName(
            self,
            "Yüz verilerini dışa aktar",
            oner,
            "Zip (*.zip)",
        )
        if not yol:
            return
        try:
            hedef = disa_aktar(yol)
        except Exception as hata:
            QMessageBox.warning(self, "Dışa aktar", str(hata))
            return
        QMessageBox.information(
            self,
            "Dışa aktar",
            f"Yüzler kaydedildi:\n{hedef}\n\n"
            "Bu zip'i diğer PC'de KobiCAM → Kişi ve Yüz Yönetimi → İçe aktar ile açın.",
        )

    def _ice_aktar(self) -> None:
        from utils.face_transfer import ice_aktar

        cevap = QMessageBox.question(
            self,
            "İçe aktar",
            "Bu paketteki yüzler mevcut galerinin yerini alır "
            "(şimdiki faces.db yedeklenir). Devam edilsin mi?",
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return
        yol, _ = QFileDialog.getOpenFileName(
            self,
            "Yüz paketi seç",
            "",
            "Zip (*.zip)",
        )
        if not yol:
            return
        try:
            n = ice_aktar(yol)
        except Exception as hata:
            QMessageBox.warning(self, "İçe aktar", str(hata))
            return
        self._imza = None
        self._yenile()
        self.galeri_degisti.emit()
        QMessageBox.information(self, "İçe aktar", f"{n} kişi yüklendi. Yüz tanımayı bir kez kapatıp açın.")
