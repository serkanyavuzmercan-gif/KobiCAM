"""
RTSP kayıt oturumu.

Görüntü her zaman kopyalanır (yeniden sıkıştırılmaz).
MP4, kameraların sık kullandığı pcm_alaw / pcm_mulaw sesini taşıyamaz;
bu yüzden MP4'te ses AAC'ye çevrilir. MKV'de ses de kopyalanır.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from process_util import ffmpeg_kapat
from utils.path_helper import get_ffmpeg_path


def ffmpeg_yolu() -> str | None:
    """PATH, PyInstaller paketi veya imageio-ffmpeg içindeki ikiliyi döndürür."""
    return get_ffmpeg_path()


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

        if self._proc.stderr is not None:
            threading.Thread(
                target=self._stderr_bosalt,
                args=(self._proc,),
                daemon=True,
            ).start()

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
        ffmpeg_kapat(proc, nazik=True, bekle_q=4.0, bekle_term=2.0)
        self.state_changed.emit(False)

    def _stderr_bosalt(self, proc: subprocess.Popen[bytes]) -> None:
        if proc.stderr is None:
            return
        try:
            while proc.poll() is None:
                if not proc.stderr.read(4096):
                    break
        except Exception:
            pass

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
        ffmpeg_kapat(self._proc, nazik=False)
        self._proc = None
        self.state_changed.emit(False)
        if kod not in (0, 255):
            mesaj = stderr.decode("utf-8", errors="replace").strip()
            self.failed.emit(mesaj or f"Kayıt süreci hata kodu {kod} ile çıktı.")


class SegmentRecorder(QObject):
    """Seçili kameralar için arka plan segment kaydı (Drive senkronu)."""

    segment_ready = pyqtSignal(str, str)  # camera_id, dosya yolu
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._surecler: dict[str, subprocess.Popen[bytes]] = {}
        self._klasorler: dict[str, Path] = {}
        self._bilinen: dict[str, set[str]] = {}
        self._izleyici = QTimer(self)
        self._izleyici.setInterval(4000)
        self._izleyici.timeout.connect(self._tara)

    def start_cameras(self, kameralar: list[dict], kok: Path, sure: int) -> None:
        self.stop()
        ffmpeg = ffmpeg_yolu()
        if not ffmpeg:
            self.failed.emit("FFmpeg bulunamadı; bulut kaydı başlatılamadı.")
            return
        from config_manager import kamera_rtsp

        bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        sure = max(60, int(sure or 300))
        for kam in kameralar:
            kid = str(kam.get("id") or "")
            url = kamera_rtsp(kam, prefer_sub=True)
            if not kid or not url:
                continue
            hedef = kok / kid
            hedef.mkdir(parents=True, exist_ok=True)
            sablon = str(hedef / "%Y%m%d_%H%M%S.mp4")
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
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-f",
                "segment",
                "-segment_time",
                str(sure),
                "-reset_timestamps",
                "1",
                "-strftime",
                "1",
                sablon,
            ]
            try:
                proc = subprocess.Popen(
                    komut,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=bayrak,
                )
            except OSError as hata:
                self.failed.emit(f"Segment kaydı başlatılamadı: {hata}")
                continue
            self._surecler[kid] = proc
            self._klasorler[kid] = hedef
            self._bilinen[kid] = {p.name for p in hedef.glob("*.mp4")}
        if self._surecler:
            self._izleyici.start()

    def stop(self) -> None:
        self._izleyici.stop()
        for kid, proc in list(self._surecler.items()):
            ffmpeg_kapat(proc, nazik=True, bekle_q=3.0, bekle_term=2.0)
            self._kapananlari_yayinla(kid, son=True)
        self._surecler.clear()
        self._klasorler.clear()
        self._bilinen.clear()

    def _tara(self) -> None:
        for kid in list(self._surecler):
            proc = self._surecler.get(kid)
            if proc is not None and proc.poll() is not None:
                self._kapananlari_yayinla(kid, son=True)
                self._surecler.pop(kid, None)
                continue
            self._kapananlari_yayinla(kid, son=False)

    def _kapananlari_yayinla(self, kid: str, son: bool) -> None:
        klasor = self._klasorler.get(kid)
        if klasor is None:
            return
        dosyalar = sorted(klasor.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        if not dosyalar:
            return
        if not son and len(dosyalar) > 0:
            dosyalar = dosyalar[:-1]
        bilinen = self._bilinen.setdefault(kid, set())
        for yol in dosyalar:
            if yol.name in bilinen:
                continue
            if yol.stat().st_size < 1024:
                continue
            bilinen.add(yol.name)
            self.segment_ready.emit(kid, str(yol))

