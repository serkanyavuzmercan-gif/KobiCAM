"""Analitik: sayım çizgisi, canlı sayaçlar, saatlik grafik."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPointF, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, uygulama_ikonu
from analytics_worker import (
    AnalyticsWorker,
    analitik_csv_yaz,
    cizgi_yan_polygon,
    grafik_y_ust,
    saat_etiketi_yerel,
    saatlik_bugun,
    yerel_utc_parantez,
)
from config_manager import ConfigManager, kamera_rtsp

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
except Exception:
    FigureCanvasQTAgg = None  # type: ignore
    Figure = None  # type: ignore


class _SayacKutu(QLabel):
    """Görüntünün köşesinde tıklanınca yer değiştiren Giren/Çıkan/Tekrar kutusu."""

    _kose_ad = ("br", "bl", "tl", "tr")

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._kose = 0
        self.setText("Giren: 0\nÇıkan: 0\nTekrar: 0")
        self.setStyleSheet(
            "QLabel { background: rgba(12,16,22,220); color:#e8edf5; border:1px solid #3a4454; "
            "border-radius:8px; padding:8px 12px; font-weight:600; }"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.adjustSize()
        self.show()
        QTimer.singleShot(0, self._yerlestir)

    def guncelle(self, giren: int, cikan: int, tekrar: int) -> None:
        self.setText(f"Giren: {giren}\nÇıkan: {cikan}\nTekrar: {tekrar}")
        self.adjustSize()
        self._yerlestir()

    def mousePressEvent(self, event) -> None:
        self._kose = (self._kose + 1) % 4
        self._yerlestir()
        event.accept()

    def _yerlestir(self) -> None:
        ebeveyn = self.parentWidget()
        if ebeveyn is None or ebeveyn.width() < 2:
            return
        self.adjustSize()
        m, w, h = 12, self.width(), self.height()
        pw, ph = ebeveyn.width(), ebeveyn.height()
        kose = self._kose_ad[self._kose]
        if kose == "br":
            self.move(max(m, pw - w - m), max(m, ph - h - m))
        elif kose == "bl":
            self.move(m, max(m, ph - h - m))
        elif kose == "tl":
            self.move(m, m)
        else:
            self.move(max(m, pw - w - m), m)
        self.raise_()


class _CizgiEtiket(QLabel):
    cizgi_degisti = pyqtSignal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._noktalar: list[tuple[float, float]] = []
        self._pm = QPixmap()
        self.setStyleSheet("background:#0b0d10; color:#8b95a8;")
        self.setText("Kamera karesi bekleniyor…")
        self._sayac_kutu = _SayacKutu(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sayac_kutu._yerlestir()

    def set_sayac(self, giren: int, cikan: int, tekrar: int) -> None:
        self._sayac_kutu.guncelle(giren, cikan, tekrar)

    def bekle(self, metin: str) -> None:
        self._pm = QPixmap()
        self.setPixmap(QPixmap())
        self.setText(metin)

    def set_pixmap_np(self, bgr) -> None:
        import numpy as np

        dizi = np.asarray(bgr)
        h, w, _ = dizi.shape
        rgb = dizi[:, :, ::-1].copy()
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        self._pm = QPixmap.fromImage(qimg.copy())
        self._ciz()

    def set_line(self, cizgi: list[float]) -> None:
        if len(cizgi) == 4:
            self._noktalar = [(cizgi[0], cizgi[1]), (cizgi[2], cizgi[3])]
            self._ciz()

    def line_norm(self) -> list[float]:
        if len(self._noktalar) < 2:
            return []
        (x1, y1), (x2, y2) = self._noktalar[:2]
        return [x1, y1, x2, y2]

    def mousePressEvent(self, event) -> None:
        if self._pm.isNull() or self.width() < 2 or self.height() < 2:
            return
        pm_w, pm_h = self._pm.width(), self._pm.height()
        if pm_w < 1 or pm_h < 1:
            return
        olcek = min(self.width() / pm_w, self.height() / pm_h)
        w, h = pm_w * olcek, pm_h * olcek
        ox = (self.width() - w) / 2
        oy = (self.height() - h) / 2
        px = event.position().x() - ox
        py = event.position().y() - oy
        if px < 0 or py < 0 or px > w or py > h:
            return
        x = min(1.0, max(0.0, px / max(1.0, w)))
        y = min(1.0, max(0.0, py / max(1.0, h)))
        if len(self._noktalar) >= 2:
            self._noktalar = []
        self._noktalar.append((x, y))
        self._ciz()
        if len(self._noktalar) == 2:
            self.cizgi_degisti.emit(self.line_norm())

    def _ciz(self) -> None:
        if self._pm.isNull():
            return
        goster = self._pm.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._noktalar:
            p = QPainter(goster)
            if len(self._noktalar) >= 2:
                gw, gh = goster.width(), goster.height()
                giris, cikis, p1, p2 = cizgi_yan_polygon(self.line_norm(), gw, gh, 16.0)
                p.setBrush(QBrush(QColor(64, 224, 208, 90)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in giris]))
                p.setBrush(QBrush(QColor(124, 58, 237, 90)))
                p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in cikis]))
                p.setPen(QPen(QColor(240, 240, 240), 3))
                p.drawLine(int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]))
                p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
                gx = int((giris[2][0] + giris[3][0]) / 2)
                gy = int((giris[2][1] + giris[3][1]) / 2)
                cx = int((cikis[2][0] + cikis[3][0]) / 2)
                cy = int((cikis[2][1] + cikis[3][1]) / 2)
                p.setPen(QColor(64, 224, 208))
                p.drawText(gx - 18, gy, "Giriş")
                p.setPen(QColor(180, 120, 255))
                p.drawText(cx - 18, cy, "Çıkış")
            p.setPen(QPen(QColor(64, 224, 208), 3))
            gw, gh = goster.width(), goster.height()
            for nx, ny in self._noktalar:
                p.drawEllipse(int(nx * gw) - 4, int(ny * gh) - 4, 8, 8)
            p.end()
        self.setPixmap(goster)


class AnalyticsDialog(QDialog):
    """İnsan trafiği izleme penceresi."""

    def __init__(self, config: ConfigManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._isci: AnalyticsWorker | None = None
        self.setWindowTitle(f"{APP_DISPLAY_NAME} — Analitik")
        self.setWindowIcon(uygulama_ikonu())
        self.resize(900, 720)
        self.setStyleSheet("QDialog { background:#1a1d23; } QLabel { color:#c5cdd8; }")

        kok = QVBoxLayout(self)
        ust = QHBoxLayout()
        self._kamera = QComboBox()
        for kam in config.cameras():
            kid = str(kam.get("id") or "")
            ad = str(kam.get("name") or kid or "Kamera")
            self._kamera.addItem(ad, kid)
        hedef = str(config.get("analytics_camera_id") or "")
        idx = self._kamera.findData(hedef)
        if idx >= 0:
            self._kamera.setCurrentIndex(idx)
        self._kamera.currentIndexChanged.connect(self._kamera_degisti)
        baslat = QPushButton("Analizi başlat")
        durdur = QPushButton("Durdur")
        kaydet = QPushButton("Çizgiyi kaydet")
        csv_btn = QPushButton("Rapor CSV")
        baslat.clicked.connect(self._baslat)
        durdur.clicked.connect(self._durdur)
        kaydet.clicked.connect(self._cizgi_kaydet)
        csv_btn.clicked.connect(self._csv_aktar)
        ust.addWidget(self._kamera, 1)
        ust.addWidget(baslat)
        ust.addWidget(durdur)
        ust.addWidget(kaydet)
        ust.addWidget(csv_btn)
        kok.addLayout(ust)

        self._durum = QLabel("Kameraya bağlanılıyor…")
        self._durum.setWordWrap(True)
        self._durum.setStyleSheet("color:#7eb8f7;")
        kok.addWidget(self._durum)
        self._sayac = QLabel("Ort. kalma: 0 sn")
        kok.addWidget(self._sayac)
        self._renk_ipucu = QLabel("Turkuaz = giriş tarafı    Mor = çıkış tarafı    (tersse çizgiyi ters yönde yeniden çizin)")
        self._renk_ipucu.setWordWrap(True)
        self._renk_ipucu.setStyleSheet("color:#8b95a8; font-size:12px;")
        kok.addWidget(self._renk_ipucu)
        self._goruntu = _CizgiEtiket()
        self._goruntu.cizgi_degisti.connect(self._cizgi_canli)
        cizgi = config.get("analytics_line") or []
        if isinstance(cizgi, list) and len(cizgi) == 4:
            self._goruntu.set_line([float(x) for x in cizgi])
        kok.addWidget(self._goruntu, 1)

        if FigureCanvasQTAgg is not None and Figure is not None:
            self._fig = Figure(figsize=(7, 2.4), facecolor="#1a1d23")
            self._ax = self._fig.add_subplot(111)
            self._ax.set_facecolor("#12151a")
            self._canvas = FigureCanvasQTAgg(self._fig)
            kok.addWidget(self._canvas)
        else:
            self._fig = None
            self._canvas = None
        self._son_grafik = 0.0
        self._grafik_yenile()
        QTimer.singleShot(0, self._baslat)

    def _secili(self) -> dict[str, Any]:
        kid = str(self._kamera.currentData() or "")
        kam = self._config.camera_by_id(kid) if kid else None
        return dict(kam) if kam else {}

    def _durum_yaz(self, metin: str) -> None:
        self._durum.setText(metin)

    def _kamera_degisti(self, _i: int = 0) -> None:
        self._baslat()

    def _baslat(self) -> None:
        kam = self._secili()
        if not kam:
            self._durum_yaz("Listede kamera yok. Önce bir cihaz ekleyin.")
            QMessageBox.warning(self, "Analitik", "Önce bir kamera ekleyin.")
            return
        if not kamera_rtsp(kam):
            self._durum_yaz("Bu kameranın RTSP adresi yok.")
            QMessageBox.warning(self, "Analitik", "Bu kameranın RTSP adresi yok.")
            return
        self._durdur(durum_yaz=False)
        self._durum_yaz("Kameraya bağlanılıyor…")
        self._goruntu.bekle("Kameraya bağlanılıyor…")
        cizgi = self._goruntu.line_norm() or list(self._config.get("analytics_line") or [])
        if not isinstance(cizgi, list) or len(cizgi) != 4:
            cizgi = []
        fps = int(self._config.get("analytics_fps") or 5)
        self._isci = AnalyticsWorker(kam, [float(x) for x in cizgi] if cizgi else [], fps, self)
        self._isci.sayac.connect(self._sayac_guncelle)
        self._isci.kare.connect(self._kare)
        self._isci.hata.connect(self._durum_yaz)
        self._isci.start()
        self._config.set("analytics_camera_id", str(kam.get("id") or ""), kaydet=True)

    def _durdur(self, durum_yaz: bool = True) -> None:
        if self._isci is None:
            return
        self._isci.request_stop()
        self._isci.wait(4000)
        self._isci = None
        if durum_yaz:
            self._durum_yaz("Durduruldu.")

    def _cizgi_canli(self, cizgi: list) -> None:
        if len(cizgi) != 4:
            return
        self._config.set("analytics_line", [float(x) for x in cizgi], kaydet=True)
        if self._isci is not None:
            self._isci.set_cizgi([float(x) for x in cizgi])
        self._durum_yaz("Çizgi ayarlandı. Kişi sayımı başlıyor…")

    def _cizgi_kaydet(self) -> None:
        cizgi = self._goruntu.line_norm()
        if len(cizgi) != 4:
            self._durum_yaz("Kaydetmek için kareye iki kez tıklayıp çizgi çizin.")
            return
        self._cizgi_canli(cizgi)
        self._durum_yaz("Çizgi kaydedildi. Turkuaz tarafa gidenler giren, mor tarafa gidenler çıkan.")

    def _csv_aktar(self) -> None:
        kam = self._secili()
        kid = str(kam.get("id") or "")
        if not kid:
            QMessageBox.warning(self, "Analitik", "Önce bir kamera seçin.")
            return
        ad = str(kam.get("name") or kid)
        gun = datetime.now().strftime("%Y-%m-%d")
        onerilen = f"KobiCAM-analitik-{ad}-{gun}.csv"
        yol, _ = QFileDialog.getSaveFileName(
            self,
            "Analitik raporu",
            onerilen,
            "CSV (*.csv)",
        )
        if not yol:
            return
        try:
            n = analitik_csv_yaz(Path(yol), kid, ad)
        except OSError as hata:
            QMessageBox.warning(self, "Analitik", f"CSV yazılamadı: {hata}")
            return
        self._durum_yaz(f"CSV kaydedildi ({n} olay): {yol}")
        QMessageBox.information(
            self,
            "Analitik",
            f"{n} olay kaydedildi.\nDosyada günlük, haftalık ve aylık rapor da vardır.",
        )

    @pyqtSlot(int, int, float, int)
    def _sayac_guncelle(self, giren: int, cikan: int, ort: float, tekrar: int = 0) -> None:
        self._sayac.setText(f"Ort. kalma: {ort:.0f} sn")
        self._goruntu.set_sayac(giren, cikan, tekrar)
        if time.monotonic() - self._son_grafik >= 2:
            self._son_grafik = time.monotonic()
            self._grafik_yenile()

    @pyqtSlot(object)
    def _kare(self, bgr) -> None:
        try:
            self._goruntu.set_pixmap_np(bgr)
        except Exception:
            pass

    def _grafik_yenile(self) -> None:
        if self._canvas is None or self._fig is None:
            return
        from matplotlib.ticker import MaxNLocator

        kam = self._secili()
        kid = str(kam.get("id") or "")
        veri = saatlik_bugun(kid) if kid else []
        self._ax.clear()
        self._ax.set_facecolor("#12151a")
        maks = 0
        if veri:
            etiket = [saat_etiketi_yerel(v[0]) + "h" for v in veri]
            giren = [v[1] for v in veri]
            cikan = [v[2] for v in veri]
            maks = max(giren + cikan)
            self._ax.bar([i - 0.15 for i in range(len(veri))], giren, 0.3, label="Giren", color="#3d9cf0")
            self._ax.bar([i + 0.15 for i in range(len(veri))], cikan, 0.3, label="Çıkan", color="#c42b2b")
            self._ax.set_xticks(range(len(veri)), etiket)
            self._ax.legend(facecolor="#1a1d23", labelcolor="#e8edf5")
        self._ax.set_ylim(0, grafik_y_ust(maks))
        self._ax.yaxis.set_major_locator(MaxNLocator(integer=True, min_n_ticks=4))
        self._ax.tick_params(colors="#8b95a8")
        self._ax.set_title(f"Bugün — yerel saat ({yerel_utc_parantez()})", color="#e8edf5", fontsize=10)
        self._fig.tight_layout()
        self._canvas.draw_idle()

    def closeEvent(self, event) -> None:
        self._durdur()
        super().closeEvent(event)
