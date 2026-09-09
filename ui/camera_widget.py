"""
Tek kamera hücresi.

Üst ikon çubuğu: yakalama, kayıt, ses, dijital zoom, HD ve (varsa) PTZ.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QToolButton,
    QWidget,
)

from audio_player import AudioPlayer
from ptz_controller import YONLER, ptz_durdur, ptz_hareket, ptz_kesfet
from record_session import RecordSession
from stream_worker import StreamWorker
from ui.bar_icons import (
    ikon_buyutec,
    ikon_hd,
    ikon_hoparlor,
    ikon_kayit,
    ikon_ok,
    ikon_yakala,
)

KAMERA_MIME = "application/x-kobicam-id"
_ZOOM_MIN = 1.0
_ZOOM_MAX = 8.0


def _dosya_parca(ad: str) -> str:
    temiz = re.sub(r'[<>:"/\\|?*\s]+', "_", ad).strip("_")
    return (temiz or "kamera")[:50]


def _ikon_dugme(tooltip: str, checkable: bool = False) -> QToolButton:
    btn = QToolButton()
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(22, 22)
    btn.setIconSize(QSize(16, 16))
    btn.setAutoRaise(True)
    btn.setCheckable(checkable)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


class _PtzKesif(QThread):
    """ONVIF PTZ yeteneğini arka planda sorgular."""

    sonuc = pyqtSignal(dict)

    def __init__(self, ip: str, kullanici: str, sifre: str, xaddrs: str) -> None:
        super().__init__()
        self._ip = ip
        self._kullanici = kullanici
        self._sifre = sifre
        self._xaddrs = xaddrs

    def run(self) -> None:
        self.sonuc.emit(ptz_kesfet(self._ip, self._kullanici, self._sifre, self._xaddrs))


class _UstCubuk(QWidget):
    """Hücre üzerine gelince görünen küçük ikon çubuğu."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("ustCubuk")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            """
            QWidget#ustCubuk {
                background-color: rgba(18, 22, 30, 230);
                border-radius: 4px;
                border: 1px solid #3d4554;
            }
            QToolButton {
                background: transparent;
                border: none;
                padding: 1px;
            }
            QToolButton:hover { background-color: rgba(61, 156, 240, 60); border-radius: 3px; }
            QToolButton:checked { background-color: rgba(61, 156, 240, 80); border-radius: 3px; }
            """
        )

        satir = QHBoxLayout(self)
        satir.setContentsMargins(4, 2, 4, 2)
        satir.setSpacing(2)

        self.btn_kare = _ikon_dugme("Ekran yakalama")
        self.btn_kare.setIcon(ikon_yakala())

        self.btn_kayit = _ikon_dugme("Video kayıt", checkable=True)
        self.btn_kayit.setObjectName("rec")
        self.btn_kayit.setIcon(ikon_kayit(False))

        self.btn_ses = _ikon_dugme("Canlı ses aç/kapat", checkable=True)
        self.btn_ses.setIcon(ikon_hoparlor(False))

        self.btn_zoom = _ikon_dugme("Dijital zoom")
        self.btn_zoom.setIcon(ikon_buyutec())

        self.btn_hd = _ikon_dugme("Görüntü kalitesi SD / HD", checkable=True)
        self.btn_hd.setIcon(ikon_hd(False))

        satir.addWidget(self.btn_kare)
        satir.addWidget(self.btn_kayit)
        satir.addWidget(self.btn_ses)
        satir.addWidget(self.btn_zoom)
        satir.addWidget(self.btn_hd)

        self._ptz_ayirici = QWidget()
        self._ptz_ayirici.setFixedWidth(6)
        satir.addWidget(self._ptz_ayirici)

        self.btn_sol = _ikon_dugme("PTZ sola")
        self.btn_sol.setIcon(ikon_ok("left"))
        self.btn_yukari = _ikon_dugme("PTZ yukarı")
        self.btn_yukari.setIcon(ikon_ok("up"))
        self.btn_asagi = _ikon_dugme("PTZ aşağı")
        self.btn_asagi.setIcon(ikon_ok("down"))
        self.btn_sag = _ikon_dugme("PTZ sağa")
        self.btn_sag.setIcon(ikon_ok("right"))

        for b in (self.btn_sol, self.btn_yukari, self.btn_asagi, self.btn_sag):
            satir.addWidget(b)

        self.ptz_dugmeleri = (self.btn_sol, self.btn_yukari, self.btn_asagi, self.btn_sag)
        self.set_ptz_visible(False)
        self.setFixedHeight(28)
        self.setMinimumWidth(130)
        self.hide()

    def set_recording(self, aktif: bool) -> None:
        self.btn_kayit.blockSignals(True)
        self.btn_kayit.setChecked(aktif)
        self.btn_kayit.setIcon(ikon_kayit(aktif))
        self.btn_kayit.blockSignals(False)

    def set_hd(self, yuksek: bool) -> None:
        self.btn_hd.blockSignals(True)
        self.btn_hd.setChecked(yuksek)
        self.btn_hd.setIcon(ikon_hd(yuksek))
        self.btn_hd.blockSignals(False)

    def set_audio(self, acik: bool) -> None:
        self.btn_ses.blockSignals(True)
        self.btn_ses.setChecked(acik)
        self.btn_ses.setIcon(ikon_hoparlor(acik))
        self.btn_ses.blockSignals(False)

    def set_ptz_visible(self, goster: bool) -> None:
        self._ptz_ayirici.setVisible(goster)
        for b in self.ptz_dugmeleri:
            b.setVisible(goster)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None and getattr(parent, "_overlay", None) is self:
            parent._overlay_konumla()

    def set_aktif(self, aktif: bool) -> None:
        """Boş hücrede ikonlar tıklanamaz."""
        for b in (
            self.btn_kare,
            self.btn_kayit,
            self.btn_ses,
            self.btn_zoom,
            self.btn_hd,
        ):
            b.setEnabled(aktif)
        if not aktif:
            self.set_ptz_visible(False)


class CameraWidget(QWidget):
    """Bir ızgara hücresinde tek kamera görüntüsü."""

    double_clicked = pyqtSignal()
    clicked = pyqtSignal()
    camera_dropped = pyqtSignal(str)
    snapshot_requested = pyqtSignal()
    snapshot_saved = pyqtSignal(str)
    record_toggled = pyqtSignal(bool)
    record_failed = pyqtSignal(str)
    quality_changed = pyqtSignal(dict)
    audio_failed = pyqtSignal(str)

    _ses_kaynak: CameraWidget | None = None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(160, 90)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

        self._kamera: dict | None = None
        self._prefer_sub = True
        self._main_on_zoom = True
        self._aktif_url = ""
        self._worker: StreamWorker | None = None
        self._pixmap = QPixmap()
        self._hata = ""
        self._secili = False

        self._zoom = _ZOOM_MIN
        self._cx = 0.5
        self._cy = 0.5
        self._surukle: str | None = None
        self._surukle_bas: QPoint = QPoint()
        self._surukle_son: QPoint = QPoint()
        self._pan_bas_merkez = QPointF(0.5, 0.5)

        self._medya_klasor = Path.home() / "Videos" / "KobiCAM"
        self._snapshot_klasor = self._medya_klasor
        self._snapshot_fmt = "png"
        self._kayit_fmt = "mp4"

        self._kayit = RecordSession(self)
        self._kayit.state_changed.connect(self._kayit_durumu)
        self._kayit.failed.connect(self._kayit_hatasi)

        self._ses = AudioPlayer(self)
        self._ses.state_changed.connect(self._ses_durumu)
        self._ses.failed.connect(self._ses_hatasi)

        self._ptz_kesif: _PtzKesif | None = None

        self._overlay = _UstCubuk(self)
        self._overlay.btn_kayit.clicked.connect(self._kayit_tik)
        self._overlay.btn_kare.clicked.connect(self.snapshot)
        self._overlay.btn_hd.clicked.connect(self._kalite_tik)
        self._overlay.btn_zoom.clicked.connect(self._buyutec_tik)
        self._overlay.btn_ses.clicked.connect(self._ses_tik)
        self._overlay.btn_sol.pressed.connect(lambda: self._ptz_basla("left"))
        self._overlay.btn_sag.pressed.connect(lambda: self._ptz_basla("right"))
        self._overlay.btn_yukari.pressed.connect(lambda: self._ptz_basla("up"))
        self._overlay.btn_asagi.pressed.connect(lambda: self._ptz_basla("down"))
        self._overlay.btn_sol.released.connect(self._ptz_birak)
        self._overlay.btn_sag.released.connect(self._ptz_birak)
        self._overlay.btn_yukari.released.connect(self._ptz_birak)
        self._overlay.btn_asagi.released.connect(self._ptz_birak)

        self._overlay.hide()
        self._cubuk_guncelleniyor = False

        self.setObjectName("CameraWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "CameraWidget, QWidget#CameraWidget { background-color: #0b0d10; }"
        )

    @property
    def camera(self) -> dict | None:
        return self._kamera

    def set_selected(self, secili: bool) -> None:
        self._secili = secili
        self.update()

    def set_media_options(
        self,
        klasor: Path,
        snapshot_fmt: str,
        kayit_fmt: str,
        snapshot_klasor: Path | None = None,
    ) -> None:
        self._medya_klasor = Path(klasor)
        self._snapshot_klasor = Path(snapshot_klasor) if snapshot_klasor else Path(klasor)
        self._snapshot_fmt = "jpg" if snapshot_fmt.lower() in ("jpg", "jpeg") else "png"
        self._kayit_fmt = "mkv" if kayit_fmt.lower() == "mkv" else "mp4"

    def set_stream_prefs(self, prefer_sub: bool, main_on_zoom: bool) -> None:
        if self._prefer_sub == prefer_sub and self._main_on_zoom == main_on_zoom:
            return
        self._prefer_sub = prefer_sub
        self._main_on_zoom = main_on_zoom
        if self._kamera is not None:
            self._akisi_guncelle()
        self._overlay_kalite_guncelle()

    def set_use_substream(self, use_sub: bool) -> None:
        """Izgara sub/main tercihi; dijital zoom main'e zorlayabilir."""
        self.set_stream_prefs(use_sub, self._main_on_zoom)

    def bind_camera(self, kamera: dict | None, use_substream: bool) -> None:
        """Kamerayı hücreye bağlar ve uygun akışı başlatır."""
        if kamera is None:
            self.stop_recording()
            self.stop_audio()
            self.reset_zoom()
            self._kamera = None
            self.stop_stream()
            self._pixmap = QPixmap()
            self._hata = ""
            self._overlay.set_ptz_visible(False)
            self._overlay.set_aktif(False)
            if self.underMouse():
                self._cubugu_goster()
            else:
                self._overlay.hide()
            self.update()
            return
        self._kamera = kamera
        self._prefer_sub = use_substream
        self._akisi_guncelle()
        self._overlay_kalite_guncelle()
        self._overlay.set_aktif(True)
        self._ptz_hazirla()
        if self.underMouse():
            self._cubugu_goster()

    def _hedef_url(self) -> str:
        if not self._kamera:
            return ""
        sub = (self._kamera.get("sub_url") or "").strip()
        main = (self._kamera.get("main_url") or "").strip()
        use_sub = self._sub_kullan()
        if use_sub and sub:
            return sub
        return main

    def _sub_kullan(self) -> bool:
        """Kamera kalitesi veya genel tercih; zoom HD'ye zorlayabilir."""
        use_sub = not self._hedef_kalite_yuksek()
        if self._zoom > 1.01 and self._main_on_zoom:
            use_sub = False
        return use_sub

    def _hedef_kalite_yuksek(self) -> bool:
        """Zoom hariç, bu hücrenin seçili kalitesi."""
        if self._kamera is None:
            return False
        kalite = str(self._kamera.get("quality") or "").lower()
        if kalite == "high":
            return True
        if kalite == "low":
            return False
        return not self._prefer_sub

    def _overlay_kalite_guncelle(self) -> None:
        self._overlay.set_hd(self._hedef_kalite_yuksek())

    def _akisi_guncelle(self) -> None:
        url = self._hedef_url()
        if not url:
            self.stop_stream()
            self._aktif_url = ""
            self._pixmap = QPixmap()
            self._hata = "RTSP adresi yok — kamerayı düzenleyin."
            self.update()
            return
        if url == self._aktif_url and self._worker is not None and self._worker.isRunning():
            return
        self._baslat(url)

    def _baslat(self, url: str) -> None:
        self.stop_stream()
        self._aktif_url = url
        self._hata = "Bağlanıyor…"
        self._pixmap = QPixmap()
        self.update()
        self._worker = StreamWorker(url)
        self._worker.frame_ready.connect(self._kare_geldi)
        self._worker.stream_error.connect(self._akis_hatasi)
        self._worker.start()

    def resume_if_needed(self) -> None:
        """Gizlendikten sonra tekrar görünür olunca akışı sürdürür."""
        if self._kamera is not None:
            self._akisi_guncelle()

    def stop_stream(self, wait: bool = True) -> None:
        """Hücredeki görüntü işçisini durdurur (kayıt ayrı kesilir)."""
        worker = self.detach_worker()
        if worker is None:
            return
        worker.request_stop()
        if wait:
            worker.wait(3000)
            worker.deleteLater()
        else:
            worker.finished.connect(worker.deleteLater)

    def detach_worker(self) -> StreamWorker | None:
        if self._worker is None:
            self._aktif_url = ""
            return None
        worker = self._worker
        self._worker = None
        self._aktif_url = ""
        try:
            worker.frame_ready.disconnect(self._kare_geldi)
        except TypeError:
            pass
        try:
            worker.stream_error.disconnect(self._akis_hatasi)
        except TypeError:
            pass
        return worker

    def stop_recording(self) -> None:
        self._kayit.stop()

    def stop_audio(self) -> None:
        if CameraWidget._ses_kaynak is self:
            CameraWidget._ses_kaynak = None
        self._ses.stop()
        self._overlay.set_audio(False)

    def _kare_geldi(self, image: QImage) -> None:
        self._pixmap = QPixmap.fromImage(image)
        self._hata = ""
        self.update()

    def _akis_hatasi(self, mesaj: str) -> None:
        self._hata = mesaj
        self.update()

    # --- medya ---

    def snapshot(self) -> None:
        """O anki tam kareyi varsayılan klasöre kaydeder."""
        if self._pixmap.isNull() or self._kamera is None:
            return
        self._snapshot_klasor.mkdir(parents=True, exist_ok=True)
        ad = _dosya_parca(str(self._kamera.get("name") or self._kamera.get("ip") or "kamera"))
        zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
        yol = self._snapshot_klasor / f"{ad}_{zaman}.{self._snapshot_fmt}"
        if self._snapshot_fmt == "jpg":
            ok = self._pixmap.save(str(yol), "JPG", 90)
        else:
            ok = self._pixmap.save(str(yol), "PNG")
        if ok:
            self.snapshot_saved.emit(str(yol))
            self.snapshot_requested.emit()
        else:
            self._hata = "Anlık görüntü yazılamadı."
            self.update()

    def _kayit_tik(self, checked: bool) -> None:
        if checked:
            self._kayit_baslat()
        else:
            self.stop_recording()

    def _kayit_baslat(self) -> None:
        url = self._aktif_url or self._hedef_url()
        if not url or self._kamera is None:
            self._overlay.set_recording(False)
            self.record_failed.emit("Kayıt için canlı akış yok.")
            return
        self._medya_klasor.mkdir(parents=True, exist_ok=True)
        ad = _dosya_parca(str(self._kamera.get("name") or self._kamera.get("ip") or "kamera"))
        zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
        yol = self._medya_klasor / f"{ad}_{zaman}.{self._kayit_fmt}"
        if not self._kayit.start(url, yol):
            self._overlay.set_recording(False)

    def _kayit_durumu(self, aktif: bool) -> None:
        self._overlay.set_recording(aktif)
        self.record_toggled.emit(aktif)
        self.update()

    def _kayit_hatasi(self, mesaj: str) -> None:
        self._overlay.set_recording(False)
        self.record_failed.emit(mesaj)
        self.update()

    def toggle_recording(self) -> None:
        """Kısayol/menü için kayıt aç-kapat."""
        if self._kamera is None:
            return
        if self._kayit.kaydediyor:
            self.stop_recording()
        else:
            self._kayit_baslat()

    def toggle_audio(self) -> None:
        """Kısayol/menü için canlı ses aç-kapat."""
        if self._kamera is None:
            return
        self._ses_tik(not self._ses.calisiyor)

    def toggle_quality(self) -> None:
        """Kısayol/menü için SD/HD geçişi."""
        if self._kamera is None:
            return
        self._kalite_tik(not self._hedef_kalite_yuksek())

    def reset_zoom(self) -> None:
        self._zoom = _ZOOM_MIN
        self._cx = 0.5
        self._cy = 0.5
        self._surukle = None
        self.update()
        if self._kamera is not None:
            self._akisi_guncelle()
        self._overlay_kalite_guncelle()

    def _kalite_tik(self, checked: bool) -> None:
        """Hücre overlay'inden SD/HD geçişi; kameraya yazılır."""
        if self._kamera is None:
            self._overlay.set_hd(False)
            return
        self._kamera["quality"] = "high" if checked else "low"
        self.quality_changed.emit(dict(self._kamera))
        self._akisi_guncelle()
        self._overlay_kalite_guncelle()

    def _buyutec_tik(self) -> None:
        """Büyüteç: 1x iken yakınlaştır, zoom'dayken sıfırla."""
        if self._kamera is None or self._pixmap.isNull():
            return
        if self._zoom > 1.01:
            self.reset_zoom()
            return
        self._zoom = min(_ZOOM_MAX, 2.0)
        self._cx = 0.5
        self._cy = 0.5
        self._akisi_guncelle()
        self._overlay_kalite_guncelle()
        self.update()

    def _ses_tik(self, checked: bool) -> None:
        if not checked:
            self.stop_audio()
            return
        url = self._aktif_url or self._hedef_url()
        if not url:
            self._overlay.set_audio(False)
            self.audio_failed.emit("Ses için canlı akış yok.")
            return
        if CameraWidget._ses_kaynak is not None and CameraWidget._ses_kaynak is not self:
            CameraWidget._ses_kaynak.stop_audio()
        CameraWidget._ses_kaynak = self
        if not self._ses.start(url):
            self._overlay.set_audio(False)
            if CameraWidget._ses_kaynak is self:
                CameraWidget._ses_kaynak = None

    def _ses_durumu(self, acik: bool) -> None:
        self._overlay.set_audio(acik)
        if not acik and CameraWidget._ses_kaynak is self:
            CameraWidget._ses_kaynak = None

    def _ses_hatasi(self, mesaj: str) -> None:
        self._overlay.set_audio(False)
        if CameraWidget._ses_kaynak is self:
            CameraWidget._ses_kaynak = None
        self.audio_failed.emit(mesaj)

    def _ptz_hazirla(self) -> None:
        if self._kamera is None:
            self._overlay.set_ptz_visible(False)
            return
        if self._kamera.get("ptz") is True and self._kamera.get("ptz_url"):
            self._overlay.set_ptz_visible(True)
            return
        if self._kamera.get("ptz") is False:
            self._overlay.set_ptz_visible(False)
            return
        self._overlay.set_ptz_visible(False)
        if self._ptz_kesif is not None and self._ptz_kesif.isRunning():
            return
        self._ptz_kesif = _PtzKesif(
            str(self._kamera.get("ip") or ""),
            str(self._kamera.get("username") or ""),
            str(self._kamera.get("password") or ""),
            str(self._kamera.get("xaddrs") or ""),
        )
        self._ptz_kesif.sonuc.connect(self._ptz_sonuc)
        self._ptz_kesif.start()

    def _ptz_sonuc(self, bilgi: dict) -> None:
        if self._kamera is None:
            return
        self._kamera["ptz"] = bool(bilgi.get("ptz"))
        self._kamera["ptz_url"] = bilgi.get("ptz_url") or ""
        self._kamera["ptz_token"] = bilgi.get("ptz_token") or ""
        self._overlay.set_ptz_visible(bool(bilgi.get("ptz")))
        self.quality_changed.emit(dict(self._kamera))

    def _ptz_basla(self, yon: str) -> None:
        if not self._kamera or not self._kamera.get("ptz"):
            return
        x, y = YONLER.get(yon, (0.0, 0.0))
        threading.Thread(
            target=ptz_hareket,
            args=(
                str(self._kamera.get("ptz_url") or ""),
                str(self._kamera.get("ptz_token") or ""),
                str(self._kamera.get("username") or ""),
                str(self._kamera.get("password") or ""),
                x,
                y,
            ),
            daemon=True,
        ).start()

    def _ptz_birak(self) -> None:
        if not self._kamera or not self._kamera.get("ptz"):
            return
        threading.Thread(
            target=ptz_durdur,
            args=(
                str(self._kamera.get("ptz_url") or ""),
                str(self._kamera.get("ptz_token") or ""),
                str(self._kamera.get("username") or ""),
                str(self._kamera.get("password") or ""),
            ),
            daemon=True,
        ).start()

    # --- geometri / zoom ---

    def _letterbox(self) -> QRect:
        alan = self._video_rect()
        if self._pixmap.isNull() or alan.isEmpty():
            return QRect()
        boyut = self._pixmap.size().scaled(
            alan.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        x = alan.x() + (alan.width() - boyut.width()) // 2
        y = alan.y() + (alan.height() - boyut.height()) // 2
        return QRect(x, y, boyut.width(), boyut.height())

    def _kaynak_rect(self) -> QRectF:
        pw = float(self._pixmap.width())
        ph = float(self._pixmap.height())
        if pw <= 0 or ph <= 0:
            return QRectF()
        sw = pw / self._zoom
        sh = ph / self._zoom
        sx = self._cx * pw - sw / 2.0
        sy = self._cy * ph - sh / 2.0
        sx = max(0.0, min(sx, pw - sw))
        sy = max(0.0, min(sy, ph - sh))
        return QRectF(sx, sy, sw, sh)

    def _merkezi_sinirla(self) -> None:
        pw = float(max(1, self._pixmap.width()))
        ph = float(max(1, self._pixmap.height()))
        yari_x = (1.0 / self._zoom) / 2.0
        yari_y = (1.0 / self._zoom) / 2.0
        self._cx = min(max(self._cx, yari_x), 1.0 - yari_x)
        self._cy = min(max(self._cy, yari_y), 1.0 - yari_y)
        if self._zoom <= 1.01:
            self._cx, self._cy = 0.5, 0.5

    def _widget_to_pixmap(self, pos: QPoint) -> QPointF | None:
        dest = self._letterbox()
        if dest.isEmpty() or not dest.contains(pos):
            return None
        src = self._kaynak_rect()
        nx = (pos.x() - dest.x()) / dest.width()
        ny = (pos.y() - dest.y()) / dest.height()
        return QPointF(src.x() + nx * src.width(), src.y() + ny * src.height())

    # --- olaylar ---

    def enterEvent(self, event) -> None:
        self._cubugu_goster()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            return
        self._overlay.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:
        self._overlay_konumla()
        super().resizeEvent(event)

    def _cubugu_goster(self) -> None:
        if self._cubuk_guncelleniyor:
            return
        self._cubuk_guncelleniyor = True
        try:
            self._overlay.set_aktif(self._kamera is not None)
            self._overlay.show()
            self._overlay.raise_()
            self._overlay_konumla()
        finally:
            self._cubuk_guncelleniyor = False

    def _overlay_konumla(self) -> None:
        ipucu = self._overlay.sizeHint()
        w = max(ipucu.width(), self._overlay.minimumWidth(), 130)
        h = 28
        x = max(4, (self.width() - w) // 2)
        self._overlay.setGeometry(x, 6, w, h)
        self._overlay.raise_()

    def _video_rect(self) -> QRect:
        """Video hücreyi doldurur; ikon çubuğu üzerine biner."""
        return QRect(0, 0, self.width(), max(1, self.height()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit()
        if event.button() == Qt.MouseButton.LeftButton and not self._pixmap.isNull():
            self._surukle_bas = event.position().toPoint()
            self._surukle_son = self._surukle_bas
            if self._zoom > 1.01:
                self._surukle = "pan"
                self._pan_bas_merkez = QPointF(self._cx, self._cy)
            else:
                self._surukle = "roi"
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._overlay.isVisible():
            self._cubugu_goster()
        pos = event.position().toPoint()
        if self._surukle == "roi":
            self._surukle_son = pos
            self.update()
        elif self._surukle == "pan" and not self._pixmap.isNull():
            dest = self._letterbox()
            if dest.width() > 0 and dest.height() > 0:
                dx = pos.x() - self._surukle_bas.x()
                dy = pos.y() - self._surukle_bas.y()
                src = self._kaynak_rect()
                self._cx = self._pan_bas_merkez.x() - (dx / dest.width()) * (
                    src.width() / max(1, self._pixmap.width())
                )
                self._cy = self._pan_bas_merkez.y() - (dy / dest.height()) * (
                    src.height() / max(1, self._pixmap.height())
                )
                self._merkezi_sinirla()
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._surukle == "roi":
            kutu = QRect(self._surukle_bas, self._surukle_son).normalized()
            dest = self._letterbox()
            kutu = kutu.intersected(dest)
            if kutu.width() >= 16 and kutu.height() >= 16 and not dest.isEmpty():
                self._roi_uygula(kutu, dest)
        self._surukle = None
        self.update()
        super().mouseReleaseEvent(event)

    def _roi_uygula(self, kutu: QRect, dest: QRect) -> None:
        src = self._kaynak_rect()
        nx = (kutu.x() - dest.x()) / dest.width()
        ny = (kutu.y() - dest.y()) / dest.height()
        nw = kutu.width() / dest.width()
        nh = kutu.height() / dest.height()
        px = src.x() + nx * src.width()
        py = src.y() + ny * src.height()
        pw = nw * src.width()
        ph = nh * src.height()
        if pw < 8 or ph < 8:
            return
        self._cx = (px + pw / 2.0) / max(1, self._pixmap.width())
        self._cy = (py + ph / 2.0) / max(1, self._pixmap.height())
        zoom_x = self._pixmap.width() / pw
        zoom_y = self._pixmap.height() / ph
        self._zoom = min(_ZOOM_MAX, max(_ZOOM_MIN, min(zoom_x, zoom_y)))
        self._merkezi_sinirla()
        self._akisi_guncelle()
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._pixmap.isNull() or self._kamera is None:
            return
        adim = event.angleDelta().y()
        if adim == 0:
            return
        faktor = 1.18 if adim > 0 else 1.0 / 1.18
        yeni = min(_ZOOM_MAX, max(_ZOOM_MIN, self._zoom * faktor))
        odak = self._widget_to_pixmap(event.position().toPoint())
        eski = self._zoom
        self._zoom = yeni
        if odak is not None and self._pixmap.width() > 0:
            # İmlecin altındaki nokta sabit kalsın
            dest = self._letterbox()
            nx = (event.position().x() - dest.x()) / max(1, dest.width())
            ny = (event.position().y() - dest.y()) / max(1, dest.height())
            sw = self._pixmap.width() / self._zoom
            sh = self._pixmap.height() / self._zoom
            self._cx = (odak.x() - (nx - 0.5) * sw) / self._pixmap.width()
            self._cy = (odak.y() - (ny - 0.5) * sh) / self._pixmap.height()
        self._merkezi_sinirla()
        if (eski <= 1.01) != (self._zoom <= 1.01):
            self._akisi_guncelle()
        self._overlay_kalite_guncelle()
        self.update()
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if self._kamera is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#1a1d23; color:#e8edf5; border:1px solid #2e3440;"
            " padding:4px; }"
            "QMenu::item { padding:6px 28px 6px 28px; min-width:170px; }"
            "QMenu::item:selected { background:#2b7fc4; }"
            "QMenu::separator { height:1px; background:#2e3440; margin:4px 8px; }"
        )
        kare = menu.addAction("Anlık görüntü\tCtrl+P")
        if self._kayit.kaydediyor:
            kayit = menu.addAction("Kaydı durdur\tCtrl+R")
        else:
            kayit = menu.addAction("Kayıt başlat\tCtrl+R")
        ses = menu.addAction("Canlı ses\tCtrl+U")
        ses.setCheckable(True)
        ses.setChecked(self._ses.calisiyor)
        hd = menu.addAction("Yüksek kalite (HD)\tCtrl+E")
        hd.setCheckable(True)
        hd.setChecked(self._hedef_kalite_yuksek())
        sifir = menu.addAction("Zoom sıfırla\tCtrl+0")
        secim = menu.exec(event.globalPos())
        if secim == kare:
            self.snapshot()
        elif secim == kayit:
            if self._kayit.kaydediyor:
                self.stop_recording()
            else:
                self._kayit_baslat()
        elif secim == ses:
            self._ses_tik(ses.isChecked())
        elif secim == hd:
            self._kalite_tik(hd.isChecked())
        elif secim == sifir:
            self.reset_zoom()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(KAMERA_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasFormat(KAMERA_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        ham = bytes(event.mimeData().data(KAMERA_MIME))
        kamera_id = ham.decode("utf-8", errors="ignore")
        event.acceptProposedAction()
        if kamera_id:
            QTimer.singleShot(50, lambda kid=kamera_id: self.camera_dropped.emit(kid))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0d10"))

        if not self._pixmap.isNull():
            dest = self._letterbox()
            src = self._kaynak_rect().toAlignedRect()
            if not dest.isEmpty() and src.width() > 0 and src.height() > 0:
                painter.drawPixmap(dest, self._pixmap, src)
        else:
            painter.setPen(QColor("#3d4554"))
            painter.setFont(QFont("Segoe UI", 10))
            ad = "Boş hücre"
            if self._kamera:
                ad = str(self._kamera.get("name") or self._kamera.get("ip") or ad)
            if self._hata:
                ad = f"{ad}\n{self._hata}"
            painter.drawText(self._video_rect(), Qt.AlignmentFlag.AlignCenter, ad)

        if self._surukle == "roi":
            kutu = QRect(self._surukle_bas, self._surukle_son).normalized()
            painter.setPen(QPen(QColor("#3d9cf0"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(61, 156, 240, 40))
            painter.drawRect(kutu)

        if self._kamera and not self._pixmap.isNull():
            painter.fillRect(0, self.height() - 22, self.width(), 22, QColor(0, 0, 0, 140))
            painter.setPen(QColor("#c5cdd8"))
            painter.setFont(QFont("Segoe UI", 8))
            etiket = str(self._kamera.get("name") or "")
            if self._zoom > 1.01:
                etiket += f"  · {self._zoom:.1f}x"
            url = self._aktif_url
            sub = (self._kamera.get("sub_url") or "").strip()
            etiket += "  · sub" if sub and url == sub else "  · main"
            if self._kayit.kaydediyor:
                etiket += "  · REC"
                painter.setPen(QColor("#e85d5d"))
            painter.drawText(
                8,
                self.height() - 20,
                self.width() - 16,
                20,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                etiket,
            )

        if self._secili:
            painter.setPen(QPen(QColor("#3d9cf0"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(1, 1, self.width() - 2, self.height() - 2)
