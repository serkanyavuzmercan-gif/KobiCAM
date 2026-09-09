"""
Canlı RTSP ses oynatıcı.

Görüntü OpenCV'de kaldığı için ses ayrı FFmpeg/ffplay sürecinde açılır.
Aynı anda yalnızca bir örnek çalışır (üst katman tek hoparlör).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from record_session import ffmpeg_yolu


def ffplay_yolu() -> str | None:
    bulunan = shutil.which("ffplay")
    if bulunan:
        return bulunan
    ff = ffmpeg_yolu()
    if ff:
        kardes = Path(ff).with_name("ffplay.exe" if sys.platform == "win32" else "ffplay")
        if kardes.exists():
            return str(kardes)
    return None


class AudioPlayer(QObject):
    """RTSP sesini hoparlöre basar (video yok)."""

    state_changed = pyqtSignal(bool)
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: subprocess.Popen[bytes] | None = None
        self._izleyici = QTimer(self)
        self._izleyici.setInterval(1000)
        self._izleyici.timeout.connect(self._kontrol)

    @property
    def calisiyor(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, rtsp_url: str) -> bool:
        self.stop()
        url = (rtsp_url or "").strip()
        if not url:
            self.failed.emit("Ses için RTSP adresi yok.")
            return False

        komut = self._komut(url)
        if komut is None:
            self.failed.emit("Ses için ffplay/ffmpeg bulunamadı.")
            return False

        bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        try:
            self._proc = subprocess.Popen(
                komut,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=bayrak,
            )
        except OSError as hata:
            self.failed.emit(f"Ses başlatılamadı: {hata}")
            self._proc = None
            return False

        self._izleyici.start()
        self.state_changed.emit(True)
        return True

    def _komut(self, url: str) -> list[str] | None:
        play = ffplay_yolu()
        if play:
            return [
                play,
                "-rtsp_transport",
                "tcp",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                url,
            ]
        ff = ffmpeg_yolu()
        if not ff:
            return None
        # ffplay yoksa ffmpeg varsayılan ses aygıtına
        if sys.platform == "win32":
            return [
                ff,
                "-hide_banner",
                "-loglevel",
                "error",
                "-rtsp_transport",
                "tcp",
                "-i",
                url,
                "-vn",
                "-f",
                "wasapi",
                "default",
            ]
        return [
            ff,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            url,
            "-vn",
            "-f",
            "pulse",
            "default",
        ]

    def stop(self) -> None:
        self._izleyici.stop()
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.state_changed.emit(False)

    def _kontrol(self) -> None:
        if self._proc is None:
            self._izleyici.stop()
            return
        if self._proc.poll() is not None:
            self._izleyici.stop()
            self._proc = None
            self.state_changed.emit(False)
