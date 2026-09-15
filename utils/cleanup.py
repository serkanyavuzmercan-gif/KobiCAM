"""Tanımsız yüz ve yetim dosya temizliği."""

from __future__ import annotations

from database import face_db

TANISIZ_TTL_DK = 10


def auto_clean_unassigned_faces(dakika: int = TANISIZ_TTL_DK) -> list[int]:
    """10 dk isim verilmeyen tanımsızları ve yetim jpg'leri siler."""
    ids = face_db.tanimsiz_eski_sil(dakika=dakika)
    _yetim_sil()
    return ids


def _yetim_sil() -> None:
    kok = face_db.faces_dir()
    if not kok.is_dir():
        return
    kayitli = face_db.kayitli_gorsel_yollari()
    for yol in list(kok.rglob("*")):
        if not yol.is_file():
            continue
        if yol.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        try:
            anahtar = str(yol.resolve())
        except OSError:
            continue
        if anahtar in kayitli:
            continue
        try:
            yol.unlink()
        except OSError:
            continue
    for klasor in sorted(kok.rglob("*"), reverse=True):
        if not klasor.is_dir() or klasor == kok:
            continue
        try:
            next(klasor.iterdir())
        except StopIteration:
            try:
                klasor.rmdir()
            except OSError:
                pass
        except OSError:
            pass
