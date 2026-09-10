"""Analitik: sayım çizgisi, canlı sayaçlar, saatlik grafik."""

from __future__ import annotations

import time
from typing import Any

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DISPLAY_NAME, uygulama_ikonu
from analytics_worker import AnalyticsWorker, saatlik_bugun
from config_manager import ConfigManager, kamera_rtsp

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
except Exception:
    FigureCanvasQTAgg = None  # type: ignore
    Figure = None  # type: ignore


class _CizgiEtiket(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._noktalar: list[tuple[float, float]] = []
        self._pm = QPixmap()
        self.setStyleSheet("background:#0b0d10; color:#8b95a8;")
        self.setText("Kamera karesi bekleniyor… Çizgi için iki kez tıklayın.")

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
        if self._pm.isNull() or self.width() < 2:
            return
        x = event.position().x() / max(1, self.width())
        y = event.position().y() / max(1, self.height())
        x = min(1.0, max(0.0, x))
        y = min(1.0, max(0.0, y))
        if len(self._noktalar) >= 2:
            self._noktalar = []
        self._noktalar.append((x, y))
        self._ciz()

    def _ciz(self) -> None:
        if self._pm.isNull():
            return
        goster = self._pm.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if len(self._noktalar) >= 2:
            p = QPainter(goster)
            p.setPen(QPen(Qt.GlobalColor.cyan, 3))
            w, h = goster.width(), goster.height()
            p.drawLine(
                int(self._noktalar[0][0] * w),
                int(self._noktalar[0][1] * h),
                int(self._noktalar[1][0] * w),
                int(self._noktalar[1][1] * h),
            )
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
            self._kamera.addItem(str(kam.get("name") or kam.get("id")), kam)
        hedef = str(config.get("analytics_camera_id") or "")
        for i in range(self._kamera.count()):
            kam = self._kamera.itemData(i) or {}
            if str(kam.get("id")) == hedef:
                self._kamera.setCurrentIndex(i)
                break
        baslat = QPushButton("Analizi başlat")
        durdur = QPushButton("Durdur")
        kaydet = QPushButton("Çizgiyi kaydet")
        baslat.clicked.connect(self._baslat)
        durdur.clicked.connect(self._durdur)
        kaydet.clicked.connect(self._cizgi_kaydet)
        ust.addWidget(self._kamera, 1)
        ust.addWidget(baslat)
        ust.addWidget(durdur)
        ust.addWidget(kaydet)
        kok.addLayout(ust)

        self._sayac = QLabel("Giren: 0   Çıkan: 0   Ort. kalma: 0 sn")
        kok.addWidget(self._sayac)
        self._goruntu = _CizgiEtiket()
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

    def _secili(self) -> dict[str, Any]:
        return dict(self._kamera.currentData() or {})

    def _baslat(self) -> None:
        self._durdur()
        kam = self._secili()
        if not kamera_rtsp(kam):
            self._sayac.setText("Bu kameranın RTSP adresi yok.")
            return
        cizgi = self._goruntu.line_norm() or list(self._config.get("analytics_line") or [])
        if len(cizgi) != 4:
            self._sayac.setText("Önce kare üzerinde iki tıklama ile çizgi çizin.")
            return
        fps = int(self._config.get("analytics_fps") or 5)
        self._isci = AnalyticsWorker(kam, [float(x) for x in cizgi], fps, self)
        self._isci.sayac.connect(self._sayac_guncelle)
        self._isci.kare.connect(self._kare)
        self._isci.hata.connect(lambda m: self._sayac.setText(m))
        self._isci.start()
        self._config.set("analytics_camera_id", str(kam.get("id") or ""), kaydet=True)

    def _durdur(self) -> None:
        if self._isci is None:
            return
        self._isci.request_stop()
        self._isci.wait(4000)
        self._isci = None

    def _cizgi_kaydet(self) -> None:
        cizgi = self._goruntu.line_norm()
        if len(cizgi) != 4:
            return
        self._config.set("analytics_line", cizgi, kaydet=True)
        self._sayac.setText("Çizgi kaydedildi.")

    @pyqtSlot(int, int, float)
    def _sayac_guncelle(self, giren: int, cikan: int, ort: float) -> None:
        self._sayac.setText(f"Giren: {giren}   Çıkan: {cikan}   Ort. kalma: {ort:.0f} sn")
        if time.monotonic() - self._son_grafik >= 10:
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
        kam = self._secili()
        kid = str(kam.get("id") or "")
        veri = saatlik_bugun(kid) if kid else []
        self._ax.clear()
        self._ax.set_facecolor("#12151a")
        if veri:
            etiket = [v[0][11:13] + "h" for v in veri]
            self._ax.bar([i - 0.15 for i in range(len(veri))], [v[1] for v in veri], 0.3, label="Giren", color="#3d9cf0")
            self._ax.bar([i + 0.15 for i in range(len(veri))], [v[2] for v in veri], 0.3, label="Çıkan", color="#c42b2b")
            self._ax.set_xticks(range(len(veri)), etiket)
            self._ax.legend(facecolor="#1a1d23", labelcolor="#e8edf5")
        self._ax.tick_params(colors="#8b95a8")
        self._ax.set_title("Bugün (UTC saat)", color="#e8edf5", fontsize=10)
        self._fig.tight_layout()
        self._canvas.draw_idle()

    def closeEvent(self, event) -> None:
        self._durdur()
        super().closeEvent(event)
