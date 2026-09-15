"""Yüz profilleri: persons + face_encodings (APPDATA/faces.db)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from db_util import baglan, sema_bir_kez
from utils.path_helper import app_data_dir, faces_dir

_DDL = """
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    is_known INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS face_encodings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    encoding BLOB NOT NULL,
    image_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    quality_score REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_face_person ON face_encodings(person_id);
"""


def faces_db() -> Path:
    return app_data_dir() / "faces.db"


def _baglan() -> sqlite3.Connection:
    sema_bir_kez(faces_db(), _DDL)
    bag = baglan(faces_db())
    bag.execute("PRAGMA foreign_keys=ON")
    _quality_kolon(bag)
    return bag


def _quality_kolon(bag: sqlite3.Connection) -> None:
    anahtar = str(faces_db().resolve())
    if anahtar in _guncellenen_sema:
        return
    kolonlar = {str(r["name"]) for r in bag.execute("PRAGMA table_info(face_encodings)").fetchall()}
    if "quality_score" not in kolonlar:
        bag.execute(
            "ALTER TABLE face_encodings ADD COLUMN quality_score REAL NOT NULL DEFAULT 0"
        )
        bag.commit()
    _guncellenen_sema.add(anahtar)


def _simdi() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def vektor_blob(vec) -> bytes:
    dizi = np.asarray(vec, dtype=np.float32).reshape(-1)
    return dizi.tobytes()


def blob_vektor(ham: bytes) -> np.ndarray:
    return np.frombuffer(ham, dtype=np.float32).copy()


TANISIZ_TTL_DK = 10
MAX_ENC = 3
_guncellenen_sema: set[str] = set()


def _kapak_jpeg(crop_bgr, kenar: int = 160) -> bytes | None:
    """Kare 160px JPEG; imwrite Unicode yol sorununu aşar."""
    try:
        import cv2
    except Exception:
        return None
    img = np.asarray(crop_bgr)
    if img.size == 0:
        return None
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)
    img = np.ascontiguousarray(img)
    h, w = img.shape[:2]
    ken = max(int(h), int(w), 1)
    tuval = np.zeros((ken, ken, 3), dtype=np.uint8)
    oy, ox = (ken - h) // 2, (ken - w) // 2
    tuval[oy : oy + h, ox : ox + w] = img
    kare = np.ascontiguousarray(cv2.resize(tuval, (kenar, kenar), interpolation=cv2.INTER_LINEAR))
    ok, buf = cv2.imencode(".jpg", kare)
    if not ok:
        ok, buf = cv2.imencode(".png", kare)
    if not ok:
        return None
    return bytes(buf)


def kisi_olustur(ad: str | None = None, is_known: bool = False) -> int:
    """Yeni kişi; ad boşsa insert sonrası 'Tanımsız Kişi #{id}'."""
    with _baglan() as bag:
        cur = bag.execute(
            "INSERT INTO persons(name, is_known, created_at) VALUES (?, ?, ?)",
            ("", 1 if is_known else 0, _simdi()),
        )
        pid = int(cur.lastrowid)
        isim = (ad or "").strip() or f"Tanımsız Kişi #{pid}"
        bag.execute("UPDATE persons SET name=? WHERE id=?", (isim, pid))
        bag.commit()
    return pid


def encoding_sayisi(person_id: int) -> int:
    with _baglan() as bag:
        row = bag.execute(
            "SELECT COUNT(*) AS n FROM face_encodings WHERE person_id=?",
            (int(person_id),),
        ).fetchone()
    return int(row["n"] if row is not None else 0)


def encodings_kirp(person_id: int, en_fazla: int = MAX_ENC) -> None:
    """Kişide en net N imzayı bırakır; düşük kaliteyi diskten siler."""
    pid = int(person_id)
    with _baglan() as bag:
        satirlar = bag.execute(
            "SELECT id, image_path, quality_score FROM face_encodings "
            "WHERE person_id=? ORDER BY quality_score DESC, id DESC",
            (pid,),
        ).fetchall()
        fazla = list(satirlar[max(0, int(en_fazla)) :])
        for s in fazla:
            bag.execute("DELETE FROM face_encodings WHERE id=?", (int(s["id"]),))
        bag.commit()
    for s in fazla:
        _jpg_sil(str(s["image_path"] or ""))


def _jpg_sil(yol: str) -> None:
    if not yol:
        return
    try:
        Path(yol).unlink(missing_ok=True)
    except OSError:
        pass


def encoding_ekle(person_id: int, vec, crop_bgr=None, en_fazla: int = MAX_ENC, quality: float = 0.0) -> int:
    """Yüz vektörünü kaydeder; kişi başına en net en_fazla imza."""
    pid = int(person_id)
    skor = float(quality)
    n = encoding_sayisi(pid)
    if n >= max(1, int(en_fazla)):
        with _baglan() as bag:
            dusuk = bag.execute(
                "SELECT id, image_path, quality_score FROM face_encodings "
                "WHERE person_id=? ORDER BY quality_score ASC, id ASC LIMIT 1",
                (pid,),
            ).fetchone()
        if dusuk is None:
            return 0
        if skor <= float(dusuk["quality_score"] or 0):
            return 0
        with _baglan() as bag:
            bag.execute("DELETE FROM face_encodings WHERE id=?", (int(dusuk["id"]),))
            bag.commit()
        _jpg_sil(str(dusuk["image_path"] or ""))
    faces_dir().mkdir(parents=True, exist_ok=True)
    klasor = faces_dir() / str(pid)
    klasor.mkdir(parents=True, exist_ok=True)
    blob = vektor_blob(vec)
    with _baglan() as bag:
        cur = bag.execute(
            "INSERT INTO face_encodings(person_id, encoding, image_path, created_at, quality_score) "
            "VALUES (?, ?, '', ?, ?)",
            (pid, blob, _simdi(), skor),
        )
        eid = int(cur.lastrowid)
        gorsel = ""
        if crop_bgr is not None:
            yol = klasor / f"{eid}.jpg"
            ham = _kapak_jpeg(crop_bgr)
            if ham:
                try:
                    yol.write_bytes(ham)
                    if yol.is_file() and yol.stat().st_size > 0:
                        gorsel = str(yol.resolve())
                except OSError:
                    gorsel = ""
            bag.execute(
                "UPDATE face_encodings SET image_path=? WHERE id=?",
                (gorsel, eid),
            )
        bag.commit()
    return eid


def kisi_kapak_yolu(person_id: int, encodings: list[dict] | None = None) -> str:
    """DB yolu veya faces/{id} klasöründeki ilk görüntü."""
    pid = int(person_id)
    for enc in reversed(encodings or []):
        yol = Path(str(enc.get("image_path") or ""))
        if yol.is_file():
            return str(yol)
    if encodings is None:
        with _baglan() as bag:
            satirlar = bag.execute(
                "SELECT image_path FROM face_encodings WHERE person_id=? ORDER BY id",
                (pid,),
            ).fetchall()
        for s in reversed(list(satirlar)):
            yol = Path(str(s["image_path"] or ""))
            if yol.is_file():
                return str(yol)
    klasor = faces_dir() / str(pid)
    if klasor.is_dir():
        for ad in ("kapak.jpg", "kapak.png"):
            aday = klasor / ad
            if aday.is_file():
                return str(aday)
        dosyalar = sorted(
            [p for p in klasor.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"} and p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if dosyalar:
            return str(dosyalar[0])
    return ""


def kapak_yaz_gerekirse(person_id: int, crop_bgr) -> str:
    """Kapak yoksa JPEG yazar ve boş image_path doldurur."""
    mevcut = kisi_kapak_yolu(person_id)
    if mevcut:
        return mevcut
    ham = _kapak_jpeg(crop_bgr)
    if not ham:
        return ""
    pid = int(person_id)
    klasor = faces_dir() / str(pid)
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / "kapak.jpg"
    try:
        yol.write_bytes(ham)
    except OSError:
        return ""
    if not yol.is_file() or yol.stat().st_size <= 0:
        return ""
    gorsel = str(yol.resolve())
    with _baglan() as bag:
        bag.execute(
            "UPDATE face_encodings SET image_path=? WHERE id=("
            "SELECT id FROM face_encodings WHERE person_id=? AND "
            "(image_path='' OR image_path IS NULL) ORDER BY id LIMIT 1)",
            (gorsel, pid),
        )
        if bag.execute("SELECT changes() AS n").fetchone()["n"] == 0:
            bag.execute(
                "UPDATE face_encodings SET image_path=? WHERE id=("
                "SELECT id FROM face_encodings WHERE person_id=? ORDER BY id LIMIT 1)",
                (gorsel, pid),
            )
        bag.commit()
    return gorsel


def kisi_al(person_id: int) -> dict[str, Any] | None:
    with _baglan() as bag:
        row = bag.execute(
            "SELECT id, name, is_known, created_at FROM persons WHERE id=?",
            (int(person_id),),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "name": str(row["name"] or ""),
        "is_known": bool(row["is_known"]),
        "created_at": str(row["created_at"] or ""),
    }


def kisiler(yalniz_bilinen: bool | None = None) -> list[dict[str, Any]]:
    sql = "SELECT id, name, is_known, created_at FROM persons"
    args: tuple = ()
    if yalniz_bilinen is True:
        sql += " WHERE is_known=1"
    elif yalniz_bilinen is False:
        sql += " WHERE is_known=0"
    sql += " ORDER BY id DESC"
    with _baglan() as bag:
        satirlar = bag.execute(sql, args).fetchall()
        sonuc = []
        for row in satirlar:
            pid = int(row["id"])
            enc = bag.execute(
                "SELECT id, image_path FROM face_encodings WHERE person_id=? ORDER BY id",
                (pid,),
            ).fetchall()
            sonuc.append(
                {
                    "id": pid,
                    "name": str(row["name"] or ""),
                    "is_known": bool(row["is_known"]),
                    "created_at": str(row["created_at"] or ""),
                    "encodings": [
                        {"id": int(e["id"]), "image_path": str(e["image_path"] or "")}
                        for e in enc
                    ],
                }
            )
    return sonuc


def isim_ver(person_id: int, ad: str) -> None:
    isim = (ad or "").strip()
    if not isim:
        raise ValueError("İsim boş olamaz.")
    with _baglan() as bag:
        bag.execute(
            "UPDATE persons SET name=?, is_known=1 WHERE id=?",
            (isim, int(person_id)),
        )
        bag.commit()


def birlestir(kaynak_id: int, hedef_id: int) -> None:
    """Kaynak encodings hedefe geçer; kaynak kişi silinir."""
    kaynak, hedef = int(kaynak_id), int(hedef_id)
    if kaynak == hedef:
        return
    hedef_kisi = kisi_al(hedef)
    if hedef_kisi is None:
        raise ValueError("Hedef kişi yok.")
    with _baglan() as bag:
        bag.execute(
            "UPDATE face_encodings SET person_id=? WHERE person_id=?",
            (hedef, kaynak),
        )
        bag.execute("DELETE FROM persons WHERE id=?", (kaynak,))
        bag.commit()
    eski = faces_dir() / str(kaynak)
    yeni = faces_dir() / str(hedef)
    if eski.is_dir():
        yeni.mkdir(parents=True, exist_ok=True)
        for dosya in eski.iterdir():
            if not dosya.is_file():
                continue
            hedef_yol = yeni / dosya.name
            try:
                dosya.replace(hedef_yol)
            except OSError:
                continue
            with _baglan() as bag:
                bag.execute(
                    "UPDATE face_encodings SET image_path=? WHERE id=? AND person_id=?",
                    (str(hedef_yol), int(dosya.stem) if dosya.stem.isdigit() else -1, hedef),
                )
                bag.commit()
        try:
            eski.rmdir()
        except OSError:
            pass
    encodings_kirp(hedef, MAX_ENC)


def benzerleri_birlestir(esik: float = 0.50) -> int:
    """Yakın imzalı kişileri birleştirir. İki kayıtlı (isimli) kişiye dokunmaz."""
    mat, ids, _adlar, known = galeri()
    if mat.shape[0] < 2:
        return 0
    unique = list(dict.fromkeys(ids))
    parent = {pid: pid for pid in unique}
    known_map: dict[int, bool] = {}
    for pid, kn in zip(ids, known):
        known_map[pid] = bool(kn) or known_map.get(pid, False)

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        ka, kb = known_map.get(ra, False), known_map.get(rb, False)
        if ka and kb:
            return
        if kb and not ka:
            parent[ra] = rb
            return
        if ka and not kb:
            parent[rb] = ra
            return
        if ra < rb:
            parent[rb] = ra
        else:
            parent[ra] = rb

    mn = np.linalg.norm(mat, axis=1, keepdims=True)
    mn = np.maximum(mn, 1e-9)
    sim = (mat / mn) @ (mat / mn).T
    n = mat.shape[0]
    for i in range(n):
        for j in range(i + 1, n):
            if ids[i] == ids[j]:
                continue
            if float(sim[i, j]) > esik:
                union(int(ids[i]), int(ids[j]))

    say = 0
    for pid in unique:
        kok = find(pid)
        if pid == kok:
            continue
        if kisi_al(pid) is None or kisi_al(kok) is None:
            continue
        birlestir(pid, kok)
        say += 1
    return say


def kisi_sil(person_id: int) -> None:
    pid = int(person_id)
    with _baglan() as bag:
        yollar = [
            str(r["image_path"] or "")
            for r in bag.execute(
                "SELECT image_path FROM face_encodings WHERE person_id=?",
                (pid,),
            ).fetchall()
        ]
        bag.execute("DELETE FROM persons WHERE id=?", (pid,))
        bag.commit()
    for yol in yollar:
        try:
            Path(yol).unlink(missing_ok=True)
        except OSError:
            pass
    klasor = faces_dir() / str(pid)
    if klasor.is_dir():
        for dosya in klasor.iterdir():
            try:
                dosya.unlink()
            except OSError:
                pass
        try:
            klasor.rmdir()
        except OSError:
            pass


def tanimsiz_eski_sil(dakika: int = TANISIZ_TTL_DK) -> list[int]:
    """Tanımlanmamış kişileri N dakika sonra siler. Kayıtlı kişilere dokunmaz."""
    kesim = datetime.now(timezone.utc) - timedelta(minutes=max(1, int(dakika)))
    esik = kesim.strftime("%Y-%m-%dT%H:%M:%SZ")
    with _baglan() as bag:
        satirlar = bag.execute(
            "SELECT id FROM persons WHERE is_known=0 AND created_at < ?",
            (esik,),
        ).fetchall()
    ids = [int(r["id"]) for r in satirlar]
    for pid in ids:
        kisi_sil(pid)
    return ids


def kayitli_gorsel_yollari() -> set[str]:
    """DB'deki tüm yüz jpg yolları (resolve)."""
    yollar: set[str] = set()
    with _baglan() as bag:
        satirlar = bag.execute("SELECT image_path FROM face_encodings").fetchall()
    for s in satirlar:
        ham = str(s["image_path"] or "").strip()
        if not ham:
            continue
        try:
            yollar.add(str(Path(ham).resolve()))
        except OSError:
            yollar.add(ham)
    return yollar


def kisi_klasor_idleri() -> set[int]:
    with _baglan() as bag:
        satirlar = bag.execute("SELECT id FROM persons").fetchall()
    return {int(r["id"]) for r in satirlar}


def galeri() -> tuple[np.ndarray, list[int], list[str], list[int]]:
    """(N,D) vektörler, encoding person_id, isim, is_known (0/1)."""
    with _baglan() as bag:
        satirlar = bag.execute(
            "SELECT e.encoding, e.person_id, p.name, p.is_known "
            "FROM face_encodings e JOIN persons p ON p.id=e.person_id"
        ).fetchall()
    if not satirlar:
        return np.zeros((0, 512), dtype=np.float32), [], [], []
    vektorler = [blob_vektor(s["encoding"]) for s in satirlar]
    dim = max(v.shape[0] for v in vektorler)
    mat = np.zeros((len(vektorler), dim), dtype=np.float32)
    for i, v in enumerate(vektorler):
        n = min(dim, v.shape[0])
        mat[i, :n] = v[:n]
    ids = [int(s["person_id"]) for s in satirlar]
    adlar = [str(s["name"] or "") for s in satirlar]
    known = [int(s["is_known"] or 0) for s in satirlar]
    return mat, ids, adlar, known
