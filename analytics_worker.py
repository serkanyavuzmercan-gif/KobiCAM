"""
YOLOv8n + ByteTrack ile tek kamera insan sayımı ve kalma süresi.
Ayrı FFmpeg pipe; GUI thread kullanılmaz.
"""

from __future__ import annotations

import gc
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from app_log import get_logger
from auth_manager import get_app_data_dir
from config_manager import kamera_rtsp
from db_util import baglan, sema_bir_kez
from process_util import ffmpeg_kapat
from record_session import ffmpeg_yolu
from utils.path_helper import get_yolo_model_path

_GEN = 640
_YUK = 360
_log = get_logger("analytics")

_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    track_id INTEGER,
    dwell_sec REAL
);
CREATE TABLE IF NOT EXISTS hourly (
    camera_id TEXT NOT NULL,
    hour_start TEXT NOT NULL,
    in_count INTEGER NOT NULL DEFAULT 0,
    out_count INTEGER NOT NULL DEFAULT 0,
    avg_dwell_sec REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (camera_id, hour_start)
);
"""


def analytics_db() -> Path:
    return get_app_data_dir() / "analytics.db"


def _baglan() -> sqlite3.Connection:
    sema_bir_kez(analytics_db(), _DDL)
    return baglan(analytics_db())


def _saat_baslangic() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")


def nokta_taraf(cizgi: list[float] | tuple[float, ...], x: float, y: float) -> int:
    """Yönlü çizginin sol (+1) / sağ (-1) / üzerinde (0)."""
    x1, y1, x2, y2 = (float(v) for v in cizgi[:4])
    v = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
    if v > 1e-9:
        return 1
    if v < -1e-9:
        return -1
    return 0


def cizgi_kesisi(
    cizgi: list[float] | tuple[float, ...],
    onceki: tuple[float, float],
    simdi: tuple[float, float],
) -> str | None:
    """Normalize 0–1 çizgiyi kesen hareket: 'in' (sağ→sol) veya 'out' (sol→sağ)."""
    t0 = nokta_taraf(cizgi, onceki[0], onceki[1])
    t1 = nokta_taraf(cizgi, simdi[0], simdi[1])
    if t0 == 0 or t1 == 0 or t0 == t1:
        return None
    return "in" if t0 < t1 else "out"


def dwell_hesap(ilk_ts: float, son_ts: float, min_sn: float = 1.0) -> float | None:
    d = float(son_ts) - float(ilk_ts)
    return d if d >= min_sn else None


def kaybolan_dwell(
    ilk: dict[int, float],
    gorunen: set[int],
    simdi: float,
    min_sn: float = 1.0,
) -> list[tuple[int, float]]:
    sonuclar: list[tuple[int, float]] = []
    for tid in [t for t in list(ilk) if t not in gorunen]:
        d = dwell_hesap(ilk.pop(tid), simdi, min_sn)
        if d is not None:
            sonuclar.append((tid, d))
    return sonuclar


def olay_yaz(kamera_id: str, kind: str, track_id: int | None, dwell: float | None) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _baglan() as bag:
        bag.execute(
            "INSERT INTO events (camera_id, ts, kind, track_id, dwell_sec) VALUES (?,?,?,?,?)",
            (kamera_id, ts, kind, track_id, dwell),
        )
        saat = _saat_baslangic()
        bag.execute(
            "INSERT OR IGNORE INTO hourly (camera_id, hour_start, in_count, out_count, avg_dwell_sec) "
            "VALUES (?,?,0,0,0)",
            (kamera_id, saat),
        )
        if kind == "in":
            bag.execute(
                "UPDATE hourly SET in_count = in_count + 1 WHERE camera_id=? AND hour_start=?",
                (kamera_id, saat),
            )
        elif kind == "out":
            bag.execute(
                "UPDATE hourly SET out_count = out_count + 1 WHERE camera_id=? AND hour_start=?",
                (kamera_id, saat),
            )
        elif kind == "dwell" and dwell is not None:
            bag.execute(
                "UPDATE hourly SET avg_dwell_sec = "
                "(avg_dwell_sec * out_count + ?) / CASE WHEN out_count < 1 THEN 1 ELSE out_count END "
                "WHERE camera_id=? AND hour_start=?",
                (float(dwell), kamera_id, saat),
            )
        bag.commit()


def saatlik_bugun(kamera_id: str) -> list[tuple[str, int, int, float]]:
    gun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _baglan() as bag:
        satirlar = bag.execute(
            "SELECT hour_start, in_count, out_count, avg_dwell_sec FROM hourly "
            "WHERE camera_id=? AND hour_start LIKE ? ORDER BY hour_start",
            (kamera_id, f"{gun}%"),
        ).fetchall()
    return [(str(a), int(b), int(c), float(d)) for a, b, c, d in satirlar]


def saatlik_son_24saat(kamera_id: str) -> tuple[int, int, float]:
    """Son 24 saatte (giren, çıkan, ortalama kalma süresi saniye)."""
    kesim = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:00:00Z")
    with _baglan() as bag:
        satirlar = bag.execute(
            "SELECT in_count, out_count, avg_dwell_sec FROM hourly "
            "WHERE camera_id=? AND hour_start>=?",
            (kamera_id, kesim),
        ).fetchall()
    giren = sum(int(a) for a, _b, _c in satirlar)
    cikan = sum(int(b) for _a, b, _c in satirlar)
    if cikan <= 0:
        return giren, cikan, 0.0
    agirlik = sum(float(c) * int(b) for _a, b, c in satirlar)
    return giren, cikan, agirlik / cikan


def model_yolu() -> Path:
    return get_yolo_model_path()


def _cuda_temizle() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


class AnalyticsWorker(QThread):
    """RTSP'den düşük FPS kare alır; kişi çizgisi ve dwell hesaplar."""

    sayac = pyqtSignal(int, int, float)  # giren, cikan, ort_dwell
    kare = pyqtSignal(object)  # numpy BGR
    hata = pyqtSignal(str)

    def __init__(self, kamera: dict[str, Any], cizgi: list[float], fps: int, parent=None) -> None:
        super().__init__(parent)
        self._kamera = kamera
        self._cizgi = list(cizgi or [])
        self._fps = max(1, min(15, int(fps or 5)))
        self._dur = False
        self._giren = 0
        self._cikan = 0
        self._dwell_toplam = 0.0
        self._dwell_n = 0
        self._ilk: dict[int, float] = {}
        self._konum: dict[int, tuple[float, float]] = {}

    def request_stop(self) -> None:
        self._dur = True

    def run(self) -> None:
        try:
            self._calis()
        except Exception as hata:
            _log.exception("Analitik")
            self.hata.emit(str(hata))

    def _calis(self) -> None:
        import numpy as np
        import subprocess
        import sys

        try:
            from ultralytics import YOLO
            import supervision as sv
        except ImportError:
            self.hata.emit("Analitik paketleri yok (ultralytics, supervision). pip install -r requirements.txt")
            return

        url = kamera_rtsp(self._kamera, prefer_sub=True)
        if not url:
            self.hata.emit("Analitik için RTSP adresi yok.")
            return
        ffmpeg = ffmpeg_yolu()
        if not ffmpeg:
            self.hata.emit("FFmpeg bulunamadı.")
            return

        try:
            yol = model_yolu()
        except FileNotFoundError as hata:
            self.hata.emit(str(hata))
            return
        model = YOLO(str(yol))
        kare_boy = _GEN * _YUK * 3
        if len(self._cizgi) != 4:
            self.hata.emit("Sayım çizgisi tanımlayın (Analitik penceresi).")
            return
        x1, y1, x2, y2 = (float(x) for x in self._cizgi)
        start = sv.Point(int(x1 * _GEN), int(y1 * _YUK))
        end = sv.Point(int(x2 * _GEN), int(y2 * _YUK))
        zone = sv.LineZone(start=start, end=end)
        annot = sv.LineZoneAnnotator(thickness=2, text_thickness=1, text_scale=0.4)

        komut = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            url,
            "-an",
            "-vf",
            f"fps={self._fps},scale={_GEN}:{_YUK}",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            komut,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=kare_boy,
            creationflags=bayrak,
        )
        kid = str(self._kamera.get("id") or "")
        son_gui = 0.0
        n_kare = 0
        try:
            while not self._dur and proc.stdout:
                ham = proc.stdout.read(kare_boy)
                if not ham or len(ham) < kare_boy:
                    break
                frame = np.frombuffer(ham, dtype=np.uint8).reshape((_YUK, _GEN, 3)).copy()
                sonuclar = model.track(
                    frame,
                    persist=True,
                    classes=[0],
                    verbose=False,
                    tracker="bytetrack.yaml",
                )
                detections = sv.Detections.from_ultralytics(sonuclar[0])
                zone.trigger(detections)
                if zone.in_count > self._giren:
                    for _ in range(zone.in_count - self._giren):
                        olay_yaz(kid, "in", None, None)
                    self._giren = int(zone.in_count)
                if zone.out_count > self._cikan:
                    for _ in range(zone.out_count - self._cikan):
                        olay_yaz(kid, "out", None, None)
                    self._cikan = int(zone.out_count)

                ids = detections.tracker_id
                xyxy = detections.xyxy
                simdi = time.monotonic()
                gorunen: set[int] = set()
                if ids is not None:
                    for i, tid in enumerate(ids):
                        if tid is None:
                            continue
                        tid = int(tid)
                        gorunen.add(tid)
                        self._ilk.setdefault(tid, simdi)
                        if xyxy is not None and i < len(xyxy):
                            kutu = xyxy[i]
                            cx = float((kutu[0] + kutu[2]) / 2) / _GEN
                            cy = float((kutu[1] + kutu[3]) / 2) / _YUK
                            once = self._konum.get(tid)
                            self._konum[tid] = (cx, cy)
                            if once is not None:
                                yon = cizgi_kesisi(self._cizgi, once, (cx, cy))
                                if yon:
                                    pass
                for tid, dwell in kaybolan_dwell(self._ilk, gorunen, simdi):
                    self._konum.pop(tid, None)
                    self._dwell_toplam += dwell
                    self._dwell_n += 1
                    olay_yaz(kid, "dwell", tid, dwell)
                ort = (self._dwell_toplam / self._dwell_n) if self._dwell_n else 0.0
                n_kare += 1
                if time.monotonic() - son_gui >= 0.5:
                    cizili = annot.annotate(frame, zone)
                    self.kare.emit(cizili)
                    son_gui = time.monotonic()
                self.sayac.emit(self._giren, self._cikan, ort)
                if n_kare % 300 == 0:
                    _cuda_temizle()
                del sonuclar, detections, frame
        finally:
            ffmpeg_kapat(proc, nazik=False, bekle_term=2.0)
            self._ilk.clear()
            self._konum.clear()
            try:
                del model
            except Exception:
                pass
            _cuda_temizle()
