"""
RTSP akış işçisi.

Her kamera ayrı bir FFmpeg sürecinde çözülür. OpenCV aynı süreçte
birden fazla RTSP açınca (2–3. kamerada) tüm uygulamayı kapatıyordu.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from record_session import ffmpeg_yolu

_GENISLIK = 960
_YUKSEKLIK = 540
_KARE_BOYUT = _GENISLIK * _YUKSEKLIK * 3
_baslangic_kilidi = threading.Lock()
_son_baslangic = 0.0


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
            bekle = 0.4 - (time.monotonic() - _son_baslangic)
            if bekle > 0:
                time.sleep(bekle)
            if not self._calisiyor:
                self._calisiyor = False
                return
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
                self.stream_error.emit(f"Akış başlatılamadı: {hata}")
                self._calisiyor = False
                return
            _son_baslangic = time.monotonic()

        proc = self._proc
        if proc.stderr is not None:
            threading.Thread(
                target=self._stderr_oku,
                args=(proc,),
                daemon=True,
            ).start()

        try:
            while self._calisiyor and not self.isInterruptionRequested():
                buf = self._kare_oku(proc)
                if buf is None:
                    mesaj = self._son_hata or "Akış açılamadı (RTSP/kimlik bilgisi)."
                    if self._calisiyor:
                        self.stream_error.emit(mesaj)
                    break
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
            self._calisiyor = False

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
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except OSError:
                    pass
        for boru in (proc.stdout, proc.stderr):
            if boru is not None:
                try:
                    boru.close()
                except Exception:
                    pass

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
        if not self.wait(3000):
            pass
