"""
RTSP kayıt oturumu.

Görüntü her zaman kopyalanır (yeniden sıkıştırılmaz).
MP4, kameraların sık kullandığı pcm_alaw / pcm_mulaw sesini taşıyamaz;
bu yüzden MP4'te ses AAC'ye çevrilir. MKV'de ses de kopyalanır.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


def ffmpeg_yolu() -> str | None:
    """PATH veya imageio-ffmpeg paketindeki ikiliyi döndürür."""
    bulunan = shutil.which("ffmpeg")
    if bulunan:
        return bulunan
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


class RecordSession(QObject):
    """Tek bir RTSP URL'sini kopyalama modunda diske kaydeder."""

    state_changed = pyqtSignal(bool)
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: subprocess.Popen[bytes] | None = None
        self._yol: Path | None = None
        self._izleyici = QTimer(self)
        self._izleyici.setInterval(800)
        self._izleyici.timeout.connect(self._kontrol)

    @property
    def kaydediyor(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def dosya_yolu(self) -> Path | None:
        return self._yol

    def start(self, rtsp_url: str, hedef: Path) -> bool:
        """Kayıt sürecini başlatır. Başarısızsa False döner."""
        self.stop()
        ffmpeg = ffmpeg_yolu()
        if not ffmpeg:
            self.failed.emit(
                "FFmpeg bulunamadı. pip install imageio-ffmpeg veya sistem PATH'e ekleyin."
            )
            return False
        url = (rtsp_url or "").strip()
        if not url:
            self.failed.emit("Kayıt için RTSP adresi yok.")
            return False

        hedef.parent.mkdir(parents=True, exist_ok=True)
        uzanti = hedef.suffix.lower()
        komut = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            url,
            "-c:v",
            "copy",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
        ]
        if uzanti == ".mp4":
            # MP4 pcm_alaw/pcm_mulaw kabul etmez; görüntü kopya, ses AAC.
            komut += [
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-ac",
                "1",
                "-movflags",
                "+frag_keyframe+empty_moov+default_base_moof",
            ]
        else:
            komut += ["-c:a", "copy"]
        komut += ["-y", str(hedef)]

        bayrak = 0
        if sys.platform == "win32":
            bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self._proc = subprocess.Popen(
                komut,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=bayrak,
            )
        except OSError as hata:
            self.failed.emit(f"FFmpeg başlatılamadı: {hata}")
            self._proc = None
            return False

        self._yol = hedef
        self._izleyici.start()
        self.state_changed.emit(True)
        return True

    def stop(self) -> None:
        """FFmpeg'e 'q' göndererek konteyneri düzgün kapatır."""
        self._izleyici.stop()
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.write(b"q")
                    proc.stdin.flush()
            except OSError:
                pass
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
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
        kod = self._proc.poll()
        if kod is None:
            return
        self._izleyici.stop()
        stderr = b""
        try:
            if self._proc.stderr:
                stderr = self._proc.stderr.read() or b""
        except OSError:
            pass
        self._proc = None
        self.state_changed.emit(False)
        if kod not in (0, 255):
            mesaj = stderr.decode("utf-8", errors="replace").strip()
            self.failed.emit(mesaj or f"Kayıt süreci hata kodu {kod} ile çıktı.")
