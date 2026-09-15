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
_TEKRAR_BEKLE_SN = 2.0
_CIZGI_MIN_UZAK = 0.02
_log = get_logger("analytics")

_OLAY_AD = {
    "in": "Giren",
    "out": "Çıkan",
    "reentry": "Tekrar giren",
    "dwell": "Kalma",
}
_GUN_ADLARI = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
_AY_ADLARI = (
    "",
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)

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
    """Turkuaz (Giriş) taraftan mor (Çıkış) tarafa geçiş = in; tersi = out."""
    t0 = nokta_taraf(cizgi, onceki[0], onceki[1])
    t1 = nokta_taraf(cizgi, simdi[0], simdi[1])
    if t0 == 0 or t1 == 0 or t0 == t1:
        return None
    return "in" if t0 < t1 else "out"


def kesenleri_uygula(
    cizgi: list[float] | tuple[float, ...],
    konum: dict[int, tuple[float, float]],
    tid: int,
    nokta: tuple[float, float],
    min_uzak: float = _CIZGI_MIN_UZAK,
) -> str | None:
    """Ayak/merkez çizginin bir tarafından diğerine geçince 'in' / 'out'."""
    taraf = nokta_taraf(cizgi, nokta[0], nokta[1])
    if taraf == 0:
        return None
    once = konum.get(tid)
    if once is None:
        konum[tid] = nokta
        return None
    yon = cizgi_kesisi(cizgi, once, nokta)
    if yon is None:
        konum[tid] = nokta
        return None
    if cizgi_uzaklik(cizgi, nokta[0], nokta[1]) >= min_uzak:
        konum[tid] = nokta
    return yon


def kutu_ayak_nokta(kutu, gen: float, yuk: float) -> tuple[float, float]:
    """Kutunun alt-orta noktası (ayak); yerdeki çizgiyi göğüs merkezi kaçırır."""
    x1, _y1, x2, y2 = (float(v) for v in kutu[:4])
    cx = ((x1 + x2) / 2.0) / max(1.0, float(gen))
    cy = float(y2) / max(1.0, float(yuk))
    return (min(1.0, max(0.0, cx)), min(1.0, max(0.0, cy)))


def cizgi_uzaklik(cizgi: list[float] | tuple[float, ...], x: float, y: float) -> float:
    x1, y1, x2, y2 = (float(v) for v in cizgi[:4])
    dx, dy = x2 - x1, y2 - y1
    uzun = (dx * dx + dy * dy) ** 0.5 or 1.0
    return abs(dx * (y - y1) - dy * (x - x1)) / uzun


def sayim_karar(
    tid: int,
    yon: str,
    simdi: float,
    durum: dict[int, dict[str, Any]],
    bekle_sn: float = _TEKRAR_BEKLE_SN,
) -> str | None:
    """
    'in' / 'out' / 'reentry' veya None (titreşim / aynı yön).
    Aynı takip önce girip çıktıktan sonra yeniden girerse tekrar giriş.
    """
    st = durum.get(tid) or {"ts": 0.0, "yon": "", "icerde": False, "girdi": False}
    if st["yon"] and (simdi - float(st["ts"])) < bekle_sn:
        return None
    if st["yon"] == yon:
        return None
    if yon == "in":
        if st["icerde"]:
            return None
        tekrar = bool(st["girdi"])
        durum[tid] = {"ts": simdi, "yon": "in", "icerde": True, "girdi": True}
        return "reentry" if tekrar else "in"
    durum[tid] = {"ts": simdi, "yon": "out", "icerde": False, "girdi": bool(st["girdi"])}
    return "out"


def cizgi_yan_polygon(
    cizgi: list[float] | tuple[float, ...],
    gen: float,
    yuk: float,
    kalinlik: float = 18.0,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]], tuple[float, float], tuple[float, float]]:
    """Giriş bandı (turkuaz, geldikleri taraf) ve çıkış bandı (mor)."""
    x1, y1, x2, y2 = (float(v) for v in cizgi[:4])
    p1 = (x1 * gen, y1 * yuk)
    p2 = (x2 * gen, y2 * yuk)
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    uzun = (dx * dx + dy * dy) ** 0.5 or 1.0
    nx = -dy / uzun * kalinlik
    ny = dx / uzun * kalinlik
    giris = [p1, p2, (p2[0] - nx, p2[1] - ny), (p1[0] - nx, p1[1] - ny)]
    cikis = [p1, p2, (p2[0] + nx, p2[1] + ny), (p1[0] + nx, p1[1] + ny)]
    return giris, cikis, p1, p2


def kareye_cizgi(
    frame,
    cizgi: list[float] | tuple[float, ...],
    giren: int,
    cikan: int,
    kutular=None,
    tekrar: int = 0,
):
    """Kişi kutularını çizer. Sayım çizgisi arayüzde bir kez çizilir."""
    import cv2

    goster = frame.copy()
    if kutular is not None:
        for kutu in kutular:
            cv2.rectangle(
                goster,
                (int(kutu[0]), int(kutu[1])),
                (int(kutu[2]), int(kutu[3])),
                (0, 200, 80),
                1,
            )
            ax = int((float(kutu[0]) + float(kutu[2])) / 2)
            ay = int(kutu[3])
            cv2.circle(goster, (ax, ay), 4, (0, 255, 255), -1)
    return goster


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


def utc_ts_yerel(ts: str) -> datetime:
    raw = str(ts).replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def _kova_bos() -> dict[str, Any]:
    return {"giren": 0, "cikan": 0, "tekrar": 0, "dwell_n": 0, "dwell_toplam": 0.0}


def _kova_ekle(kova: dict[str, Any], kind: str, dwell: float | None) -> None:
    if kind == "in":
        kova["giren"] += 1
    elif kind == "out":
        kova["cikan"] += 1
    elif kind == "reentry":
        kova["tekrar"] += 1
    elif kind == "dwell" and dwell is not None:
        kova["dwell_n"] += 1
        kova["dwell_toplam"] += float(dwell)


def _kova_ort(kova: dict[str, Any]) -> float:
    n = int(kova["dwell_n"])
    return float(kova["dwell_toplam"]) / n if n else 0.0


def rapor_grupla(olaylar: list[tuple[str, str, int | None, float | None]]) -> dict[str, Any]:
    """Olayları yerel güne / ISO haftaya / aya göre toplar."""
    genel = _kova_bos()
    gunluk: dict[str, dict[str, Any]] = {}
    haftalik: dict[tuple[int, int], dict[str, Any]] = {}
    aylik: dict[str, dict[str, Any]] = {}
    for ts, kind, _tid, dwell in olaylar:
        yerel = utc_ts_yerel(ts)
        _kova_ekle(genel, kind, dwell)
        gun_k = yerel.strftime("%Y-%m-%d")
        if gun_k not in gunluk:
            gunluk[gun_k] = _kova_bos()
            gunluk[gun_k]["gun_ad"] = _GUN_ADLARI[yerel.weekday()]
        _kova_ekle(gunluk[gun_k], kind, dwell)
        iso = yerel.isocalendar()
        h_k = (int(iso[0]), int(iso[1]))
        if h_k not in haftalik:
            pazartesi = yerel.date() - timedelta(days=yerel.weekday())
            haftalik[h_k] = _kova_bos()
            haftalik[h_k]["bas"] = pazartesi.isoformat()
            haftalik[h_k]["bit"] = (pazartesi + timedelta(days=6)).isoformat()
            haftalik[h_k]["etiket"] = f"{iso[0]}-W{int(iso[1]):02d}"
        _kova_ekle(haftalik[h_k], kind, dwell)
        ay_k = yerel.strftime("%Y-%m")
        if ay_k not in aylik:
            aylik[ay_k] = _kova_bos()
            aylik[ay_k]["etiket"] = f"{_AY_ADLARI[yerel.month]} {yerel.year}"
        _kova_ekle(aylik[ay_k], kind, dwell)
    return {"genel": genel, "gunluk": gunluk, "haftalik": haftalik, "aylik": aylik}


def _yaz_kova(yaz, bas: list[Any], kova: dict[str, Any], ekstra: list[Any] | None = None) -> None:
    yaz.writerow(
        list(bas)
        + [
            kova["giren"],
            kova["cikan"],
            kova["tekrar"],
            int(kova["giren"]) - int(kova["cikan"]),
            kova["dwell_n"],
            f"{_kova_ort(kova):.1f}",
        ]
        + list(ekstra or [])
    )


def olaylari_al(kamera_id: str) -> list[tuple[str, str, int | None, float | None]]:
    with _baglan() as bag:
        satirlar = bag.execute(
            "SELECT ts, kind, track_id, dwell_sec FROM events WHERE camera_id=? ORDER BY ts",
            (kamera_id,),
        ).fetchall()
    return [
        (str(ts), str(kind), int(tid) if tid is not None else None, float(d) if d is not None else None)
        for ts, kind, tid, d in satirlar
    ]


def analitik_csv_yaz(yol: Path, kamera_id: str, kamera_adi: str = "") -> int:
    """Olay detayı + günlük / haftalık / aylık rapor yazar. Olay satır sayısı döner."""
    import csv

    olaylar = olaylari_al(kamera_id)
    saatlik = saatlik_bugun(kamera_id)
    rapor = rapor_grupla(olaylar)
    ad = kamera_adi or kamera_id
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    baslik = ["Giren", "Cikan", "Tekrar_giren", "Net_iceride", "Kalma_adet", "Ort_kalma_sn"]
    with yol.open("w", encoding="utf-8-sig", newline="") as dosya:
        yaz = csv.writer(dosya, delimiter=";")
        yaz.writerow(["# KobiCAM analitik raporu"])
        yaz.writerow(["# Kamera", ad, kamera_id])
        yaz.writerow(["# Zaman dilimi", yerel_utc_parantez()])
        yaz.writerow(["# Olusturma", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")])
        yaz.writerow([])
        yaz.writerow(["# Genel ozet (tum kayit)"])
        yaz.writerow(baslik)
        _yaz_kova(yaz, [], rapor["genel"])
        yaz.writerow([])
        yaz.writerow(["# Aylik rapor"])
        yaz.writerow(["Ay", "Ay_adi"] + baslik + ["Gun_sayisi", "Gunluk_ort_giren"])
        for ay_k in sorted(rapor["aylik"]):
            kova = rapor["aylik"][ay_k]
            gun_n = sum(1 for g in rapor["gunluk"] if g.startswith(ay_k))
            ort_g = (kova["giren"] / gun_n) if gun_n else 0.0
            _yaz_kova(yaz, [ay_k, kova.get("etiket", ay_k)], kova, [gun_n, f"{ort_g:.1f}"])
        yaz.writerow([])
        yaz.writerow(["# Haftalik rapor (Pazartesi-Pazar, ISO hafta)"])
        yaz.writerow(["Hafta", "Baslangic", "Bitis"] + baslik)
        for h_k in sorted(rapor["haftalik"]):
            kova = rapor["haftalik"][h_k]
            _yaz_kova(yaz, [kova.get("etiket", ""), kova.get("bas", ""), kova.get("bit", "")], kova)
        yaz.writerow([])
        yaz.writerow(["# Gunluk ozet"])
        yaz.writerow(["Tarih", "Gun"] + baslik)
        for gun_k in sorted(rapor["gunluk"]):
            kova = rapor["gunluk"][gun_k]
            _yaz_kova(yaz, [gun_k, kova.get("gun_ad", "")], kova)
        yaz.writerow([])
        yaz.writerow(["# Saatlik ozet (bugun, yerel)"])
        yaz.writerow(["Saat_dilimi", "Giren", "Cikan", "Ort_kalma_sn"])
        for hour_start, giren, cikan, ort in saatlik:
            yaz.writerow([saat_etiketi_yerel(hour_start) + ":00", giren, cikan, f"{ort:.1f}"])
        yaz.writerow([])
        yaz.writerow(["# Olay detayi"])
        yaz.writerow(["Tarih", "Saat", "Saat_dilimi", "Kamera", "Kamera_id", "Olay", "Takip_no", "Kalma_sn", "UTC"])
        for ts, kind, tid, dwell in olaylar:
            yerel = utc_ts_yerel(ts)
            yaz.writerow(
                [
                    yerel.strftime("%Y-%m-%d"),
                    yerel.strftime("%H:%M:%S"),
                    yerel.strftime("%H:00"),
                    ad,
                    kamera_id,
                    _OLAY_AD.get(kind, kind),
                    tid if tid is not None else "",
                    f"{dwell:.1f}" if dwell is not None else "",
                    ts,
                ]
            )
    return len(olaylar)


def yerel_utc_parantez() -> str:
    """Örn. UTC+3 veya UTC-5:30."""
    ofset = datetime.now().astimezone().utcoffset() or timedelta(0)
    toplam = int(ofset.total_seconds() // 60)
    isaret = "+" if toplam >= 0 else "-"
    saat, dakika = divmod(abs(toplam), 60)
    if dakika:
        return f"UTC{isaret}{saat}:{dakika:02d}"
    return f"UTC{isaret}{saat}"


def saat_baslangic_yerel(hour_start: str) -> datetime:
    raw = str(hour_start).replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def saat_etiketi_yerel(hour_start: str) -> str:
    return f"{saat_baslangic_yerel(hour_start).hour:02d}"


def grafik_y_ust(maks: int) -> int:
    """Kişi sayısı için tam sayı üst sınır; 1 kişide 0–1’e kilitlenmez."""
    m = max(0, int(maks))
    if m <= 5:
        return 5
    if m <= 10:
        return 10
    if m <= 50:
        adim = 5
    elif m <= 100:
        adim = 10
    elif m <= 500:
        adim = 50
    else:
        adim = 100
    return ((m + adim - 1) // adim) * adim


def saatlik_bugun(kamera_id: str) -> list[tuple[str, int, int, float]]:
    """Yerel takvim gününün saatlik sayıları (UTC saklanır, yerel güne göre süzülür)."""
    yerel = datetime.now().astimezone()
    bas = yerel.replace(hour=0, minute=0, second=0, microsecond=0)
    bit = bas + timedelta(days=1)
    bas_utc = bas.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    bit_utc = bit.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    with _baglan() as bag:
        satirlar = bag.execute(
            "SELECT hour_start, in_count, out_count, avg_dwell_sec FROM hourly "
            "WHERE camera_id=? AND hour_start>=? AND hour_start<? ORDER BY hour_start",
            (kamera_id, bas_utc, bit_utc),
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

    sayac = pyqtSignal(int, int, float, int)  # giren, cikan, ort_dwell, tekrar
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
        self._tekrar = 0
        self._dwell_toplam = 0.0
        self._dwell_n = 0
        self._ilk: dict[int, float] = {}
        self._konum: dict[int, tuple[float, float]] = {}
        self._konum_orta: dict[int, tuple[float, float]] = {}
        self._sayim: dict[int, dict[str, Any]] = {}
        self._proc = None

    def request_stop(self) -> None:
        self._dur = True
        proc = self._proc
        if proc is not None:
            ffmpeg_kapat(proc, nazik=False, bekle_term=0.8)

    def set_cizgi(self, cizgi: list[float]) -> None:
        self._cizgi = [float(x) for x in (cizgi or [])[:4]]

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

        url = kamera_rtsp(self._kamera, prefer_sub=True)
        if not url:
            self.hata.emit("Analitik için RTSP adresi yok.")
            return
        ffmpeg = ffmpeg_yolu()
        if not ffmpeg:
            self.hata.emit("FFmpeg bulunamadı.")
            return

        self.hata.emit("Kameraya bağlanılıyor…")
        kare_boy = _GEN * _YUK * 3
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
        self._proc = proc
        kid = str(self._kamera.get("id") or "")
        son_gui = 0.0
        n_kare = 0
        model = None
        takip = None
        sv_mod = None
        son_cizgi: tuple[float, ...] | None = None
        try:
            while not self._dur and proc.stdout:
                ham = proc.stdout.read(kare_boy)
                if not ham or len(ham) < kare_boy:
                    if n_kare == 0 and not self._dur:
                        self.hata.emit("Kameradan görüntü alınamadı. RTSP veya ağı kontrol edin.")
                    break
                frame = np.frombuffer(ham, dtype=np.uint8).reshape((_YUK, _GEN, 3)).copy()
                n_kare += 1
                cizgi = list(self._cizgi)
                if len(cizgi) == 4:
                    if model is None:
                        self.hata.emit("YOLO modeli yükleniyor…")
                        try:
                            from ultralytics import YOLO
                            import supervision as sv
                        except ImportError:
                            self.hata.emit(
                                "Analitik paketleri yok (ultralytics, supervision). pip install -r requirements.txt"
                            )
                            return
                        try:
                            yol = model_yolu()
                        except FileNotFoundError as hata:
                            self.hata.emit(str(hata))
                            return
                        import warnings

                        model = YOLO(str(yol))
                        sv_mod = sv
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            takip = sv.ByteTrack(
                                frame_rate=float(self._fps),
                                lost_track_buffer=90,
                                track_activation_threshold=0.15,
                                minimum_consecutive_frames=1,
                            )
                        self.hata.emit("Sayım hazır. Çizgiyi kesen kişiler sayılır.")
                    if takip is None or sv_mod is None:
                        continue
                    anahtar = tuple(float(x) for x in cizgi)
                    if anahtar != son_cizgi:
                        self._konum.clear()
                        self._konum_orta.clear()
                        self._sayim.clear()
                        son_cizgi = anahtar
                    sonuclar = model.predict(frame, classes=[0], verbose=False, imgsz=_GEN)
                    detections = sv_mod.Detections.from_ultralytics(sonuclar[0])
                    try:
                        if len(detections) > 0 and detections.confidence is not None:
                            detections = takip.update_with_detections(detections)
                    except Exception:
                        _log.exception("ByteTrack")
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
                            if xyxy is None or i >= len(xyxy):
                                continue
                            kutu = xyxy[i]
                            h, w = frame.shape[:2]
                            ayak = kutu_ayak_nokta(kutu, w, h)
                            orta = (
                                min(1.0, max(0.0, float((kutu[0] + kutu[2]) / 2) / max(1, w))),
                                min(1.0, max(0.0, float((kutu[1] + kutu[3]) / 2) / max(1, h))),
                            )
                            yon = kesenleri_uygula(cizgi, self._konum, tid, ayak)
                            if yon is None:
                                yon = kesenleri_uygula(cizgi, self._konum_orta, tid, orta)
                            if yon is None:
                                continue
                            karar = sayim_karar(tid, yon, simdi, self._sayim)
                            if karar == "in":
                                self._giren += 1
                                olay_yaz(kid, "in", tid, None)
                            elif karar == "reentry":
                                self._tekrar += 1
                                olay_yaz(kid, "reentry", tid, None)
                            elif karar == "out":
                                self._cikan += 1
                                olay_yaz(kid, "out", tid, None)
                    for tid, dwell in kaybolan_dwell(self._ilk, gorunen, simdi):
                        self._konum.pop(tid, None)
                        self._konum_orta.pop(tid, None)
                        st = self._sayim.get(tid)
                        if st is not None:
                            st["icerde"] = False
                        self._dwell_toplam += dwell
                        self._dwell_n += 1
                        olay_yaz(kid, "dwell", tid, dwell)
                    ort = (self._dwell_toplam / self._dwell_n) if self._dwell_n else 0.0
                    if time.monotonic() - son_gui >= 0.5:
                        self.kare.emit(
                            kareye_cizgi(frame, cizgi, self._giren, self._cikan, xyxy, self._tekrar)
                        )
                        son_gui = time.monotonic()
                    self.sayac.emit(self._giren, self._cikan, ort, self._tekrar)
                    if n_kare % 300 == 0:
                        _cuda_temizle()
                    del sonuclar, detections, frame
                else:
                    if time.monotonic() - son_gui >= 0.2:
                        self.kare.emit(frame)
                        son_gui = time.monotonic()
                    if n_kare == 1:
                        self.hata.emit("Görüntü geldi. Kareye iki kez tıklayıp sayım çizgisini çizin.")
                    del frame
        finally:
            ffmpeg_kapat(proc, nazik=False, bekle_term=2.0)
            self._ilk.clear()
            self._konum.clear()
            self._konum_orta.clear()
            self._sayim.clear()
            try:
                del model
            except Exception:
                pass
            _cuda_temizle()
