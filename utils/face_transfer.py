"""Yüz galerisini zip olarak dışa/içe aktarma (başka PC)."""

from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from database import face_db
from db_util import baglan

_MANIFEST = "kobicam_faces.json"


def _wal_kes() -> None:
    yol = face_db.faces_db()
    if not yol.is_file():
        return
    with baglan(yol) as bag:
        bag.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        bag.commit()


def _gorsel_rel(person_id: int, image_path: str) -> str:
    ad = Path(str(image_path or "")).name
    if not ad:
        ad = "kapak.jpg"
    return f"faces/{int(person_id)}/{ad}"


def disa_aktar(hedef_zip: str | Path) -> Path:
    """faces.db + jpg'leri göreli yollu zip'e yazar."""
    hedef = Path(hedef_zip)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    _wal_kes()
    tmp = hedef.parent / f".kobicam_face_export_{hedef.stem}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        db_kopya = tmp / "faces.db"
        shutil.copy2(face_db.faces_db(), db_kopya)
        yuzler = tmp / "faces"
        kaynak = face_db.faces_dir()
        if kaynak.is_dir():
            shutil.copytree(kaynak, yuzler, dirs_exist_ok=True)
        else:
            yuzler.mkdir(parents=True, exist_ok=True)
        with baglan(db_kopya) as bag:
            satirlar = bag.execute(
                "SELECT id, person_id, image_path FROM face_encodings"
            ).fetchall()
            for s in satirlar:
                rel = _gorsel_rel(int(s["person_id"]), str(s["image_path"] or ""))
                bag.execute(
                    "UPDATE face_encodings SET image_path=? WHERE id=?",
                    (rel, int(s["id"])),
                )
            bag.commit()
        (tmp / _MANIFEST).write_text(
            json.dumps(
                {
                    "app": "KobiCAM",
                    "kind": "faces",
                    "version": 1,
                    "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if hedef.exists():
            hedef.unlink()
        with zipfile.ZipFile(hedef, "w", zipfile.ZIP_DEFLATED) as z:
            for dosya in tmp.rglob("*"):
                if dosya.is_file():
                    z.write(dosya, dosya.relative_to(tmp).as_posix())
        return hedef
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ice_aktar(kaynak_zip: str | Path) -> int:
    """Zip'teki galeriyi mevcut yüz verisinin yerine koyar. Dönüş: kişi sayısı."""
    arsiv = Path(kaynak_zip)
    if not arsiv.is_file():
        raise ValueError("Paket dosyası yok.")
    tmp = arsiv.parent / f".kobicam_face_import_{arsiv.stem}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(arsiv, "r") as z:
            z.extractall(tmp)
        db_gelen = tmp / "faces.db"
        if not db_gelen.is_file():
            raise ValueError("Pakette faces.db yok.")
        _wal_kes()
        hedef_db = face_db.faces_db()
        hedef_dir = face_db.faces_dir()
        if hedef_db.is_file():
            shutil.copy2(hedef_db, hedef_db.with_suffix(".db.bak"))
        shutil.copy2(db_gelen, hedef_db)
        for ek in (hedef_db.with_name(hedef_db.name + "-wal"), hedef_db.with_name(hedef_db.name + "-shm")):
            try:
                ek.unlink(missing_ok=True)
            except OSError:
                pass
        if hedef_dir.exists():
            shutil.rmtree(hedef_dir, ignore_errors=True)
        gelen_yuz = tmp / "faces"
        if gelen_yuz.is_dir():
            shutil.copytree(gelen_yuz, hedef_dir)
        else:
            hedef_dir.mkdir(parents=True, exist_ok=True)
        n = _yollari_yerellestir(hedef_db, hedef_dir)
        face_db._guncellenen_sema.discard(str(hedef_db.resolve()))
        return n
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _yollari_yerellestir(db_yol: Path, yuz_dir: Path) -> int:
    with baglan(db_yol) as bag:
        bag.execute("PRAGMA foreign_keys=ON")
        satirlar = bag.execute(
            "SELECT id, person_id, image_path FROM face_encodings"
        ).fetchall()
        for s in satirlar:
            pid = int(s["person_id"])
            eski = str(s["image_path"] or "")
            ad = Path(eski).name if eski else ""
            klasor = yuz_dir / str(pid)
            aday = klasor / ad if ad else None
            if aday is None or not aday.is_file():
                if klasor.is_dir():
                    dosyalar = sorted(
                        p for p in klasor.iterdir()
                        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
                    )
                    aday = dosyalar[0] if dosyalar else None
            gorsel = str(aday.resolve()) if aday is not None and aday.is_file() else ""
            bag.execute(
                "UPDATE face_encodings SET image_path=? WHERE id=?",
                (gorsel, int(s["id"])),
            )
        kisiler = bag.execute("SELECT COUNT(*) AS n FROM persons").fetchone()
        bag.commit()
    return int(kisiler["n"] if kisiler is not None else 0)
