"""
Yüz tespiti, cosine eşleştirme ve FaceWorker (ayrı FFmpeg, GUI dışı).

StreamWorker decode yoluna bağlanmaz.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from app_log import get_logger
from config_manager import kamera_rtsp
from database import face_db
from process_util import ffmpeg_kapat
from record_session import ffmpeg_yolu
from utils.path_helper import insightface_root
from utils.cleanup import auto_clean_unassigned_faces
from utils.face_quality import bulaniklik, kaydedilebilir

_GEN = 960
_YUK = 540
ESIK = 0.45
AYNI_ESIK = 0.42
YENI_ESIK = 0.52
FARK_ESIK = 0.08
GECIS_FARK = 0.12
COOLDOWN_ESIK = 0.50
COOLDOWN_SN = 30.0
KAYIT_COOLDOWN_SN = 30.0
ENROLL_KARE = 3
_IOU_ESIK = 0.35
_TAKIP_SN = 6.0
_MIN_YUZ = 18.0
_ENROLL_SKOR = 0.42
_SCRFD_STRIDE = (8, 16, 32)
_DET_ESIK = 0.45
_NMS_ESIK = 0.4
_ARCFACE_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)
_log = get_logger("face")


def cosine_benzerlik(a: np.ndarray, b: np.ndarray) -> float:
    va = np.asarray(a, dtype=np.float32).reshape(-1)
    vb = np.asarray(b, dtype=np.float32).reshape(-1)
    n = min(va.size, vb.size)
    if n == 0:
        return 0.0
    va = va[:n]
    vb = vb[:n]
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(va / na, vb / nb))


def en_iyi_eslesme(
    mat: np.ndarray,
    ids: list[int],
    vec: np.ndarray,
    esik: float = ESIK,
) -> tuple[int | None, float]:
    """Galeride en yüksek cosine; eşik altındaysa (None, skor)."""
    if mat is None or mat.size == 0 or not ids:
        return None, 0.0
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    dim = int(mat.shape[1])
    if v.size < dim:
        pad = np.zeros(dim, dtype=np.float32)
        pad[: v.size] = v
        v = pad
    else:
        v = v[:dim]
    vn = float(np.linalg.norm(v))
    if vn < 1e-9:
        return None, 0.0
    v = v / vn
    mn = np.linalg.norm(mat, axis=1)
    mn = np.maximum(mn, 1e-9)
    skorlar = (mat / mn[:, None]) @ v
    i = int(np.argmax(skorlar))
    skor = float(skorlar[i])
    if skor > esik:
        return int(ids[i]), skor
    return None, skor


def kisi_skorlari(mat: np.ndarray, ids: list[int], vec: np.ndarray) -> dict[int, float]:
    """Kişi başına en yüksek cosine."""
    if mat is None or mat.size == 0 or not ids:
        return {}
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    dim = int(mat.shape[1])
    if v.size < dim:
        pad = np.zeros(dim, dtype=np.float32)
        pad[: v.size] = v
        v = pad
    else:
        v = v[:dim]
    vn = float(np.linalg.norm(v))
    if vn < 1e-9:
        return {}
    v = v / vn
    mn = np.linalg.norm(mat, axis=1)
    mn = np.maximum(mn, 1e-9)
    skorlar = (mat / mn[:, None]) @ v
    out: dict[int, float] = {}
    for pid, skor in zip(ids, skorlar):
        p = int(pid)
        s = float(skor)
        if s > out.get(p, -1.0):
            out[p] = s
    return out


def kimlik_sec(
    skorlar: dict[int, float],
    kilit_pid: int | None = None,
    known: set[int] | None = None,
    esik: float = ESIK,
    tut: float = AYNI_ESIK,
    fark: float = FARK_ESIK,
    gecis: float = GECIS_FARK,
) -> int | None:
    """Kayıtlı isim, tanımsız kayıtlardan bağımsız seçilir; kilitli kutu isim zıplatmaz."""
    _ = tut
    if not skorlar:
        return int(kilit_pid) if kilit_pid is not None else None
    known_ids = {int(x) for x in (known or [])}

    def _sec(havuz: dict[int, float], kilit: int | None, min_skor: float) -> int | None:
        if not havuz:
            return None
        sira = sorted(havuz.items(), key=lambda kv: -kv[1])
        pid1, s1 = int(sira[0][0]), float(sira[0][1])
        s2 = float(sira[1][1]) if len(sira) > 1 else -1.0
        if kilit is not None and int(kilit) in havuz:
            kid = int(kilit)
            sk = float(havuz[kid])
            if pid1 != kid and s1 >= min_skor and s1 >= sk + gecis and (s1 - s2) >= fark:
                return pid1
            return kid
        if s1 >= min_skor and (s1 - s2) >= fark:
            return pid1
        return None

    if known_ids:
        named = {p: s for p, s in skorlar.items() if int(p) in known_ids}
        kilit_n = int(kilit_pid) if kilit_pid is not None and int(kilit_pid) in known_ids else None
        pid = _sec(named, kilit_n, esik)
        if pid is not None:
            return pid
        if kilit_n is not None:
            return kilit_n
        unnamed = {p: s for p, s in skorlar.items() if int(p) not in known_ids}
        if kilit_pid is not None:
            return int(kilit_pid)
        return _sec(unnamed, None, YENI_ESIK)
    return _sec(skorlar, kilit_pid, esik)


def yeni_kisi_acilabilir(
    vec: np.ndarray,
    son_yeniler: list[tuple[np.ndarray, int, float]],
    simdi: float,
    cooldown_sn: float = COOLDOWN_SN,
    cooldown_esik: float = COOLDOWN_ESIK,
) -> int | None:
    """Son cooldown içindeki benzer kişi id'si; yoksa None (yeni açılabilir)."""
    for eski, pid, ts in reversed(son_yeniler):
        if simdi - ts > cooldown_sn:
            continue
        if cosine_benzerlik(vec, eski) > cooldown_esik:
            return int(pid)
    return None


def kutu_kaliteli(bbox, gen: int, yuk: int, skor: float = 1.0) -> bool:
    """Küçük, yamuk veya düşük skorlu kutular yeni kişi açmaz."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    bw, bh = x2 - x1, y2 - y1
    if bw < _MIN_YUZ or bh < _MIN_YUZ:
        return False
    if bw > gen * 0.9 or bh > yuk * 0.9:
        return False
    oran = bw / max(bh, 1e-6)
    if oran < 0.5 or oran > 1.7:
        return False
    if float(skor) < _ENROLL_SKOR:
        return False
    return True


def _kare_crop(frame, bbox, pad: float = 0.4):
    import cv2

    h, w = frame.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in bbox)
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    kenar = max(x2 - x1, y2 - y1) * (1.0 + pad)
    kenar = max(kenar, _MIN_YUZ)
    hx = kenar / 2.0
    ix1 = int(max(0, round(cx - hx)))
    iy1 = int(max(0, round(cy - hx)))
    ix2 = int(min(w, round(cx + hx)))
    iy2 = int(min(h, round(cy + hx)))
    if ix2 <= ix1 or iy2 <= iy1:
        return None
    crop = frame[iy1:iy2, ix1:ix2]
    if crop.size == 0:
        return None
    ch, cw = crop.shape[:2]
    ken = max(ch, cw, 1)
    tuval = np.zeros((ken, ken, 3), dtype=np.uint8)
    oy, ox = (ken - ch) // 2, (ken - cw) // 2
    tuval[oy : oy + ch, ox : ox + cw] = crop
    return cv2.resize(tuval, (160, 160), interpolation=cv2.INTER_LINEAR)


def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    kes = iw * ih
    if kes <= 0:
        return 0.0
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    ba = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    birles = aa + ba - kes
    return kes / birles if birles > 0 else 0.0


def buffalo_hazir_mi() -> bool:
    det, rec = buffalo_dosyalari()
    return det is not None and rec is not None


def buffalo_dosyalari(klasor=None) -> tuple:
    """det_500m + w600k_mbf; 2d106det landmark modeli seçilmez."""
    from pathlib import Path

    kok = Path(klasor) if klasor is not None else insightface_root() / "models" / "buffalo_s"
    det = rec = None
    if kok.is_dir():
        for dosya in kok.iterdir():
            ad = dosya.name.lower()
            if ad == "det_500m.onnx" or ad.startswith("det_500"):
                det = dosya
            elif "w600k" in ad and ad.endswith(".onnx"):
                rec = dosya
    return det, rec


def _model_yukle():
    """Önce onnxruntime SCRFD+ArcFace (Py 3.14); InsightFace isteğe bağlı."""
    kok = insightface_root()
    onnx = _onnx_yukle(kok / "models" / "buffalo_s")
    if onnx is not None:
        return onnx
    if not buffalo_hazir_mi():
        return None
    try:
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(
            name="buffalo_s",
            root=str(kok),
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))
        return ("insightface", app)
    except Exception as hata:
        _log.warning("InsightFace yüklenemedi: %s", hata)
    return None


def _onnx_yukle(klasor):
    det, rec = buffalo_dosyalari(klasor)
    if det is None or rec is None:
        return None
    try:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        dses = ort.InferenceSession(str(det), so, providers=["CPUExecutionProvider"])
        rses = ort.InferenceSession(str(rec), so, providers=["CPUExecutionProvider"])
        _log.info("Yüz modeli yüklendi: SCRFD %s + ArcFace %s", det.name, rec.name)
        return ("onnx", (dses, rses))
    except Exception as hata:
        _log.warning("onnxruntime yüz modeli yok: %s", hata)
        return None


def _yuzleri_al(model, frame) -> list[dict[str, Any]]:
    if model is None:
        return []
    tur, ic = model
    if tur == "insightface":
        sonuclar = []
        for yuz in ic.get(frame) or []:
            bbox = [float(x) for x in yuz.bbox]
            emb = np.asarray(yuz.embedding, dtype=np.float32)
            sonuclar.append({"bbox": bbox, "embedding": emb, "skor": 1.0, "crop": None})
        return sonuclar
    dses, rses = ic
    return _onnx_yuzler(dses, rses, frame)


def _letterbox(frame, kenar: int = 640):
    import cv2

    h, w = frame.shape[:2]
    olcek = min(kenar / float(w), kenar / float(h))
    nw, nh = max(1, int(round(w * olcek))), max(1, int(round(h * olcek)))
    img = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    tuval = np.zeros((kenar, kenar, 3), dtype=np.uint8)
    ox, oy = (kenar - nw) // 2, (kenar - nh) // 2
    tuval[oy : oy + nh, ox : ox + nw] = img
    return tuval, olcek, ox, oy


def _nms(kutular: np.ndarray, skorlar: np.ndarray, esik: float = _NMS_ESIK) -> list[int]:
    if kutular.size == 0:
        return []
    x1, y1, x2, y2 = kutular[:, 0], kutular[:, 1], kutular[:, 2], kutular[:, 3]
    alan = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    sira = skorlar.argsort()[::-1]
    kalan: list[int] = []
    while sira.size > 0:
        i = int(sira[0])
        kalan.append(i)
        if sira.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[sira[1:]])
        yy1 = np.maximum(y1[i], y1[sira[1:]])
        xx2 = np.minimum(x2[i], x2[sira[1:]])
        yy2 = np.minimum(y2[i], y2[sira[1:]])
        kes = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = kes / (alan[i] + alan[sira[1:]] - kes + 1e-9)
        sira = sira[1:][iou <= esik]
    return kalan


def _scrfd_kutular(dses, tuval, esik: float = _DET_ESIK):
    """buffalo_s det_500m: skor / kutu / 5 nokta, stride 8-16-32, 2 çapa."""
    import cv2

    blob = cv2.dnn.blobFromImage(
        tuval, 1.0 / 128.0, (tuval.shape[1], tuval.shape[0]), (127.5, 127.5, 127.5), swapRB=True
    )
    adlar = [o.name for o in dses.get_outputs()]
    cikti = dses.run(adlar, {dses.get_inputs()[0].name: blob})
    yuk, gen = tuval.shape[0], tuval.shape[1]
    fmc = 3
    skor_l, kutu_l, kps_l = [], [], []
    for i, stride in enumerate(_SCRFD_STRIDE):
        skor = np.asarray(cikti[i]).reshape(-1)
        bbox = np.asarray(cikti[i + fmc], dtype=np.float32).reshape(-1, 4) * stride
        kps_ham = np.asarray(cikti[i + fmc * 2], dtype=np.float32).reshape(-1, 10) * stride
        gw, gh = gen // stride, yuk // stride
        if gw * gh * 2 != skor.size and gw > 0:
            gh = max(1, skor.size // (gw * 2))
        yy, xx = np.mgrid[:gh, :gw]
        merkez = np.stack((xx, yy), axis=-1).astype(np.float32).reshape(-1, 2) * stride
        merkez = np.repeat(merkez, 2, axis=0)
        n = min(skor.size, merkez.shape[0], bbox.shape[0], kps_ham.shape[0])
        skor, bbox, kps_ham, merkez = skor[:n], bbox[:n], kps_ham[:n], merkez[:n]
        pos = np.where(skor >= esik)[0]
        if pos.size == 0:
            continue
        x1 = merkez[pos, 0] - bbox[pos, 0]
        y1 = merkez[pos, 1] - bbox[pos, 1]
        x2 = merkez[pos, 0] + bbox[pos, 2]
        y2 = merkez[pos, 1] + bbox[pos, 3]
        skor_l.append(skor[pos])
        kutu_l.append(np.stack([x1, y1, x2, y2], axis=-1))
        pts = np.empty((pos.size, 5, 2), dtype=np.float32)
        kh = kps_ham[pos]
        m = merkez[pos]
        for j in range(5):
            pts[:, j, 0] = m[:, 0] + kh[:, j * 2]
            pts[:, j, 1] = m[:, 1] + kh[:, j * 2 + 1]
        kps_l.append(pts)
    if not skor_l:
        return (
            np.zeros((0, 4), np.float32),
            np.zeros((0,), np.float32),
            np.zeros((0, 5, 2), np.float32),
        )
    skorlar = np.concatenate(skor_l, axis=0)
    kutular = np.concatenate(kutu_l, axis=0)
    noktalar = np.concatenate(kps_l, axis=0)
    keep = _nms(kutular, skorlar)
    if len(keep) > 16:
        sira = np.argsort(-skorlar[keep])[:16]
        keep = [keep[int(j)] for j in sira]
    return kutular[keep], skorlar[keep], noktalar[keep]


def _arcface_hizala(frame, kps):
    import cv2

    src = np.asarray(kps, dtype=np.float32).reshape(5, 2)
    m, _ = cv2.estimateAffinePartial2D(src, _ARCFACE_DST, method=cv2.LMEDS)
    if m is None:
        return None
    return cv2.warpAffine(frame, m, (112, 112), borderValue=0.0)


def _onnx_yuzler(dses, rses, frame) -> list[dict[str, Any]]:
    """SCRFD tespit + ArcFace 512-d imza (Haar kullanılmaz)."""
    import cv2

    h, w = frame.shape[:2]
    tuval, olcek, ox, oy = _letterbox(frame, 640)
    kutular, _skorlar, noktalar = _scrfd_kutular(dses, tuval)
    inp = rses.get_inputs()[0]
    sonuclar = []
    for i, kutu in enumerate(kutular):
        x1 = (float(kutu[0]) - ox) / olcek
        y1 = (float(kutu[1]) - oy) / olcek
        x2 = (float(kutu[2]) - ox) / olcek
        y2 = (float(kutu[3]) - oy) / olcek
        x1, y1 = max(0.0, x1), max(0.0, y1)
        x2, y2 = min(float(w), x2), min(float(h), y2)
        bw, bh = x2 - x1, y2 - y1
        if bw < 8 or bh < 8:
            continue
        oran = bw / max(bh, 1e-6)
        if oran < 0.4 or oran > 2.0:
            continue
        hizali = None
        if i < len(noktalar):
            kps = noktalar[i].copy()
            kps[:, 0] = (kps[:, 0] - ox) / olcek
            kps[:, 1] = (kps[:, 1] - oy) / olcek
            hizali = _arcface_hizala(frame, kps)
        if hizali is None:
            ix1, iy1, ix2, iy2 = int(x1), int(y1), int(x2), int(y2)
            crop = frame[iy1:iy2, ix1:ix2]
            if crop.size == 0:
                continue
            hizali = cv2.resize(crop, (112, 112))
        blob = cv2.dnn.blobFromImage(
            hizali, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True
        )
        try:
            out = rses.run(None, {inp.name: blob})[0]
        except Exception:
            continue
        skor = float(_skorlar[i]) if i < len(_skorlar) else 0.0
        kapak = _kare_crop(frame, [x1, y1, x2, y2])
        if kapak is None and hizali is not None:
            kapak = hizali
        sonuclar.append(
            {
                "bbox": [x1, y1, x2, y2],
                "embedding": np.asarray(out, dtype=np.float32).reshape(-1),
                "skor": skor,
                "crop": kapak,
            }
        )
    return sonuclar


def kareye_yuzler(frame, tespitler: list[dict[str, Any]]):
    import cv2

    goster = frame.copy()
    h, w = goster.shape[:2]
    for t in tespitler:
        x1, y1, x2, y2 = t["bbox_norm"]
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        renk = (80, 200, 120) if t.get("is_known") else (40, 160, 255)
        cv2.rectangle(goster, (px1, py1), (px2, py2), renk, 2)
        ad = str(t.get("name") or "")
        if ad:
            cv2.putText(
                goster,
                ad[:42],
                (px1, max(16, py1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                renk,
                1,
                cv2.LINE_AA,
            )
    return goster


class FaceEngine:
    """Galeri + tespit + enroll (cooldown)."""

    def __init__(self) -> None:
        self._model = None
        self._mat = np.zeros((0, 512), dtype=np.float32)
        self._ids: list[int] = []
        self._adlar: list[str] = []
        self._known: list[int] = []
        self._son_yeni: list[tuple[np.ndarray, int, float]] = []
        self._takip: list[dict[str, Any]] = []
        self._tid = 0
        self._son_temizlik = 0.0
        self._son_kayit: dict[int, float] = {}
        self.yenile()

    def yenile(self) -> None:
        self._mat, self._ids, self._adlar, self._known = face_db.galeri()

    def model_hazirla(self) -> str | None:
        if self._model is not None:
            return None
        self._model = _model_yukle()
        if self._model is None:
            return (
                "Yüz modeli yok. onnxruntime ve buffalo_s (det_500m + w600k_mbf) gerekli."
            )
        try:
            n = face_db.benzerleri_birlestir(0.58)
            if n:
                _log.info("%s benzer yüz kaydı birleştirildi", n)
                self.yenile()
        except Exception:
            _log.exception("Benzer yüz birleştirme")
        return None

    def kare_isle(self, frame, simdi: float | None = None) -> list[dict[str, Any]]:
        simdi = time.monotonic() if simdi is None else float(simdi)
        self._tanimsiz_temizle(simdi)
        h, w = frame.shape[:2]
        yuzler = _yuzleri_al(self._model, frame)
        self._takip_temizle(simdi)
        yuzler = sorted(yuzler, key=lambda y: -float(y.get("skor") or 0.0))
        kullanilan_pid: set[int] = set()
        kullanilan_tid: set[int] = set()
        cikti: list[dict[str, Any]] = []
        for yuz in yuzler:
            bbox = yuz["bbox"]
            vec = np.asarray(yuz["embedding"], dtype=np.float32).reshape(-1)
            tid = self._takip_esle(bbox, simdi, haric=kullanilan_tid)
            kullanilan_tid.add(tid)
            kilit = self._takip_pid(tid)
            known_ids = {int(pid) for pid, kn in zip(self._ids, self._known) if kn}
            skorlar = kisi_skorlari(self._mat, self._ids, vec)
            for pid_k in list(skorlar):
                if pid_k in kullanilan_pid and pid_k != kilit:
                    skorlar.pop(pid_k, None)
            pid = kimlik_sec(skorlar, kilit, known=known_ids)
            kapak = yuz.get("crop")
            if kapak is None:
                kapak = _kare_crop(frame, bbox)
            if pid is None:
                pid = self._enroll(
                    vec, bbox, frame, tid, simdi, float(yuz.get("skor") or 0.0),
                    haric=kullanilan_pid,
                    crop=kapak,
                )
            else:
                self._foto_guncelle(pid, tid, vec, bbox, kapak, simdi)
            if pid is not None:
                self._takip_isaret(tid, pid)
                kullanilan_pid.add(int(pid))
            ad, known = self._kisi_etiket(pid) if pid else ("Tanımsız", False)
            x1, y1, x2, y2 = bbox
            cikti.append(
                {
                    "bbox_norm": [
                        min(1.0, max(0.0, x1 / max(1, w))),
                        min(1.0, max(0.0, y1 / max(1, h))),
                        min(1.0, max(0.0, x2 / max(1, w))),
                        min(1.0, max(0.0, y2 / max(1, h))),
                    ],
                    "name": ad,
                    "is_known": bool(known),
                    "person_id": pid,
                }
            )
        return cikti

    def _kisi_etiket(self, pid: int | None) -> tuple[str, bool]:
        if pid is None:
            return "Tanımsız", False
        kisi = face_db.kisi_al(pid)
        if kisi is None:
            return "Tanımsız", False
        return str(kisi["name"]), bool(kisi["is_known"])

    def _tanimsiz_temizle(self, simdi: float) -> None:
        if simdi - self._son_temizlik < 20.0 and self._son_temizlik > 0:
            return
        self._son_temizlik = simdi
        silinen = set(auto_clean_unassigned_faces())
        if not silinen:
            return
        self._son_yeni = [x for x in self._son_yeni if int(x[1]) not in silinen]
        self._son_kayit = {p: t for p, t in self._son_kayit.items() if p not in silinen}
        for t in self._takip:
            pid = t.get("person_id")
            if pid is not None and int(pid) in silinen:
                t["person_id"] = None
                t["aday"] = 0
        self.yenile()

    def _enroll(
        self,
        vec,
        bbox,
        frame,
        tid: int,
        simdi: float,
        skor: float = 1.0,
        haric: set[int] | None = None,
        crop=None,
    ) -> int | None:
        haric = haric or set()
        for t in self._takip:
            if t["id"] == tid and t.get("person_id"):
                return int(t["person_id"])
        mevcut = yeni_kisi_acilabilir(vec, self._son_yeni, simdi, cooldown_sn=KAYIT_COOLDOWN_SN)
        if mevcut is not None and int(mevcut) not in haric:
            kisi = face_db.kisi_al(int(mevcut))
            if kisi is None or not kisi["is_known"]:
                self._takip_isaret(tid, int(mevcut))
                return int(mevcut)
        h, w = frame.shape[:2]
        if not kutu_kaliteli(bbox, w, h, skor):
            return None
        if crop is None:
            crop = _kare_crop(frame, bbox)
        if crop is None or not kaydedilebilir(crop, bbox):
            return None
        aday = 0
        for t in self._takip:
            if t["id"] == tid:
                t["aday"] = int(t.get("aday") or 0) + 1
                aday = t["aday"]
                break
        if aday < ENROLL_KARE:
            return None
        pid = face_db.kisi_olustur()
        face_db.encoding_ekle(pid, vec, crop, quality=bulaniklik(crop))
        self._son_yeni.append((vec.copy(), pid, simdi))
        self._son_kayit[int(pid)] = simdi
        if len(self._son_yeni) > 64:
            self._son_yeni = self._son_yeni[-32:]
        self._takip_isaret(tid, pid, kayit=True, simdi=simdi)
        self.yenile()
        return pid

    def _foto_guncelle(self, pid: int, tid: int, vec, bbox, crop, simdi: float) -> None:
        """30 sn cooldown; yalnızca daha net fotoğraf 3'lü tavana girer."""
        if crop is None or not kaydedilebilir(crop, bbox):
            return
        son = self._son_kayit.get(int(pid))
        if son is not None and simdi - float(son) < KAYIT_COOLDOWN_SN:
            return
        for t in self._takip:
            if t["id"] != tid:
                continue
            kayit_ts = t.get("kayit_ts")
            if kayit_ts is not None and simdi - float(kayit_ts) < KAYIT_COOLDOWN_SN:
                return
            eid = face_db.encoding_ekle(int(pid), vec, crop, quality=bulaniklik(crop))
            if eid:
                t["kayit_ts"] = simdi
                self._son_kayit[int(pid)] = simdi
                self.yenile()
            return

    def _takip_pid(self, tid: int) -> int | None:
        for t in self._takip:
            if t["id"] == tid:
                pid = t.get("person_id")
                return int(pid) if pid else None
        return None

    def _takip_esle(self, bbox, simdi: float, haric: set[int] | None = None) -> int:
        haric = haric or set()
        kutu = [float(x) for x in bbox]
        en, kim = 0.0, -1
        for i, t in enumerate(self._takip):
            if int(t["id"]) in haric:
                continue
            u = _iou(kutu, t["bbox"])
            if u > en:
                en, kim = u, i
        if kim >= 0 and en >= _IOU_ESIK:
            self._takip[kim]["bbox"] = kutu
            self._takip[kim]["ts"] = simdi
            return int(self._takip[kim]["id"])
        self._tid += 1
        self._takip.append(
            {
                "id": self._tid,
                "bbox": kutu,
                "ts": simdi,
                "person_id": None,
                "aday": 0,
                "kayit_ts": None,
            }
        )
        return self._tid

    def _takip_isaret(self, tid: int, pid: int, kayit: bool = False, simdi: float | None = None) -> None:
        for t in self._takip:
            if t["id"] == tid:
                t["person_id"] = int(pid)
                if kayit:
                    t["kayit_ts"] = float(simdi if simdi is not None else time.monotonic())
                return

    def _takip_temizle(self, simdi: float) -> None:
        self._takip = [t for t in self._takip if simdi - float(t["ts"]) < _TAKIP_SN]


class FaceWorker(QThread):
    """Tek kamera yüz tanıma; AnalyticsWorker ile aynı FFmpeg kalıbı."""

    kare = pyqtSignal(object)
    tespitler = pyqtSignal(object)
    hata = pyqtSignal(str)

    def __init__(self, kamera: dict[str, Any], fps: int, parent=None) -> None:
        super().__init__(parent)
        self._kamera = kamera
        self._fps = max(1, min(15, int(fps or 5)))
        self._dur = False
        self._proc = None
        self._yenile = False
        self._motor: FaceEngine | None = None

    def request_stop(self) -> None:
        self._dur = True
        proc = self._proc
        if proc is not None:
            ffmpeg_kapat(proc, nazik=False, bekle_term=0.8)

    def galeri_yenile(self) -> None:
        self._yenile = True

    def run(self) -> None:
        try:
            self._calis()
        except Exception as hata:
            _log.exception("Yüz tanıma")
            self.hata.emit(str(hata))

    def _calis(self) -> None:
        import subprocess
        import sys

        url = kamera_rtsp(self._kamera, prefer_sub=False)
        if not url:
            self.hata.emit("Yüz tanıma için RTSP adresi yok.")
            return
        ffmpeg = ffmpeg_yolu()
        if not ffmpeg:
            self.hata.emit("FFmpeg bulunamadı.")
            return

        self.hata.emit("Kameraya bağlanılıyor…")
        motor = FaceEngine()
        self._motor = motor
        uyari = motor.model_hazirla()
        if uyari:
            self.hata.emit(uyari)
            return
        self.hata.emit("Yüz tanıma hazır.")

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
        n_kare = 0
        son_gui = 0.0
        try:
            while not self._dur and proc.stdout:
                ham = proc.stdout.read(kare_boy)
                if not ham or len(ham) < kare_boy:
                    if n_kare == 0 and not self._dur:
                        self.hata.emit("Kameradan görüntü alınamadı. RTSP veya ağı kontrol edin.")
                    break
                frame = np.frombuffer(ham, dtype=np.uint8).reshape((_YUK, _GEN, 3)).copy()
                n_kare += 1
                if self._yenile:
                    motor.yenile()
                    self._yenile = False
                tespit: list = []
                if motor._model is not None:
                    tespit = motor.kare_isle(frame)
                self.tespitler.emit(tespit)
                if time.monotonic() - son_gui >= 0.2:
                    self.kare.emit(kareye_yuzler(frame, tespit))
                    son_gui = time.monotonic()
                del frame
        finally:
            ffmpeg_kapat(proc, nazik=False, bekle_term=2.0)
            self._motor = None
            self._proc = None
