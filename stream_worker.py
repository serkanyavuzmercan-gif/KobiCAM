"""
RTSP akış işçisi.

Her kamera ayrı bir FFmpeg sürecinde çözülür. Kopunca aynı QThread içinde
üstel backoff ile yeniden bağlanır; GUI thread uyutulmaz.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from app_log import get_logger
from process_util import ffmpeg_kapat
from record_session import ffmpeg_yolu

_GENISLIK = 960
_YUKSEKLIK = 540
_KARE_BOYUT = _GENISLIK * _YUKSEKLIK * 3
_baslangic_kilidi = threading.Lock()
_son_baslangic = 0.0
_log = get_logger("stream")


class StreamWorker(QThread):
    """Tek bir RTSP URL'sini ayrı FFmpeg sürecinde okur."""

    frame_ready = pyqtSignal(QImage)
    stream_error = pyqtSignal(str)
    recording_state = pyqtSignal(bool)

    def __init__(self, rtsp_url: str, parent=None) -> None:
        super().__init__(parent)
        self.rtsp_url = rtsp_url
        self._calisiyor = False
        self._proc: subprocess.Popen[bytes] | None = None
        self._son_hata = ""

    def run(self) -> None:
        self._calisiyor = True
        url = (self.rtsp_url or "").strip()
        if not url:
            self.stream_error.emit("RTSP adresi boş.")
            self._calisiyor = False
            return

        ffmpeg = ffmpeg_yolu()
        if not ffmpeg:
            self.stream_error.emit("FFmpeg bulunamadı.")
            self._calisiyor = False
            return

        bekle = 2.0
        try:
            while self._calisiyor and not self.isInterruptionRequested():
                if not self._oturum(ffmpeg, url):
                    if not self._calisiyor or self.isInterruptionRequested():
                        break
                    mesaj = self._son_hata or "Akış koptu, yeniden bağlanılıyor…"
                    self.stream_error.emit(mesaj)
                    _log.warning("RTSP koptu, %.0fs sonra denenecek", bekle)
                    bitis = time.monotonic() + bekle
                    while self._calisiyor and time.monotonic() < bitis:
                        if self.isInterruptionRequested():
                            return
                        time.sleep(0.2)
                    bekle = min(30.0, bekle * 2)
                else:
                    bekle = 2.0
        except Exception:
            _log.exception("StreamWorker çöktü")
            if self._calisiyor:
                self.stream_error.emit("Akış işçisi beklenmeyen hata.")
        finally:
            self._sureci_kapat()
            self._calisiyor = False

    def _oturum(self, ffmpeg: str, url: str) -> bool:
        """True: durdurma isteğiyle çıktı. False: kopma / hata."""
        komut = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-timeout",
            "8000000",
            "-i",
            url,
            "-an",
            "-sn",
            "-vf",
            f"scale={_GENISLIK}:{_YUKSEKLIK}",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

        global _son_baslangic
        with _baslangic_kilidi:
            aralik = 0.4 - (time.monotonic() - _son_baslangic)
            if aralik > 0:
                time.sleep(aralik)
            if not self._calisiyor or self.isInterruptionRequested():
                return True
            try:
                self._proc = subprocess.Popen(
                    komut,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=_KARE_BOYUT,
                    creationflags=bayrak,
                )
            except OSError as hata:
                self._son_hata = f"Akış başlatılamadı: {hata}"
                return False
            _son_baslangic = time.monotonic()

        proc = self._proc
        if proc.stderr is not None:
            threading.Thread(
                target=self._stderr_oku,
                args=(proc,),
                daemon=True,
            ).start()

        kare_var = False
        try:
            while self._calisiyor and not self.isInterruptionRequested():
                buf = self._kare_oku(proc)
                if buf is None:
                    return (not self._calisiyor) or self.isInterruptionRequested()
                kare_var = True
                qimg = QImage(
                    buf,
                    _GENISLIK,
                    _YUKSEKLIK,
                    _GENISLIK * 3,
                    QImage.Format.Format_BGR888,
                )
                if not qimg.isNull():
                    self.frame_ready.emit(qimg.copy())
        finally:
            self._sureci_kapat()
        return kare_var and ((not self._calisiyor) or self.isInterruptionRequested())

    def _kare_oku(self, proc: subprocess.Popen[bytes]) -> bytes | None:
        if proc.stdout is None:
            return None
        buf = bytearray()
        while len(buf) < _KARE_BOYUT:
            if not self._calisiyor or self.isInterruptionRequested():
                return None
            parca = proc.stdout.read(_KARE_BOYUT - len(buf))
            if not parca:
                return None
            buf.extend(parca)
        return bytes(buf)

    def _stderr_oku(self, proc: subprocess.Popen[bytes]) -> None:
        if proc.stderr is None:
            return
        try:
            for satir in proc.stderr:
                metin = satir.decode("utf-8", errors="ignore").strip()
                if metin:
                    self._son_hata = metin[-200:]
        except Exception:
            pass

    def _sureci_kapat(self) -> None:
        proc = self._proc
        self._proc = None
        ffmpeg_kapat(proc, nazik=False, bekle_term=1.5)

    def request_stop(self) -> None:
        """Beklemeden durdurma (ızgara gizleme ve hücre değişimi)."""
        self._calisiyor = False
        self.requestInterruption()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def stop(self) -> None:
        """İşçiyi durdurur ve bitmesini bekler."""
        self.request_stop()
        self.wait(3000)
