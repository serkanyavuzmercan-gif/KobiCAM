"""Yüz tanıma: cosine, cooldown, persons CRUD. InsightFace gerekmez."""

from __future__ import annotations

import numpy as np
import pytest

from config_manager import ConfigManager
from database import face_db
from utils.face_engine import (
    AYNI_ESIK,
    COOLDOWN_ESIK,
    ENROLL_KARE,
    ESIK,
    FaceEngine,
    _nms,
    buffalo_dosyalari,
    cosine_benzerlik,
    en_iyi_eslesme,
    kimlik_sec,
    kutu_kaliteli,
    yeni_kisi_acilabilir,
)


@pytest.fixture
def yuz_db(tmp_path, monkeypatch):
    monkeypatch.setattr(face_db, "faces_db", lambda: tmp_path / "faces.db")
    monkeypatch.setattr(face_db, "faces_dir", lambda: tmp_path / "faces")
    return tmp_path


def test_cosine_esik() -> None:
    a = np.ones(512, dtype=np.float32)
    b = np.ones(512, dtype=np.float32)
    assert cosine_benzerlik(a, b) == pytest.approx(1.0)
    c = -a
    assert cosine_benzerlik(a, c) == pytest.approx(-1.0)
    d = np.zeros(512, dtype=np.float32)
    d[0] = 1.0
    e = np.zeros(512, dtype=np.float32)
    e[1] = 1.0
    assert cosine_benzerlik(d, e) == pytest.approx(0.0)
    assert ESIK == 0.45
    assert AYNI_ESIK < ESIK


def test_en_iyi_eslesme_esik() -> None:
    v = np.zeros(8, dtype=np.float32)
    v[0] = 1.0
    yakin = v.copy()
    yakin[0] = 0.95
    yakin[1] = 0.31
    uzak = np.zeros(8, dtype=np.float32)
    uzak[2] = 1.0
    mat = np.stack([uzak, yakin])
    pid, skor = en_iyi_eslesme(mat, [10, 20], v, esik=0.65)
    assert pid == 20
    assert skor > 0.65
    pid2, skor2 = en_iyi_eslesme(np.stack([uzak]), [10], yakin, esik=0.65)
    assert pid2 is None
    assert skor2 < 0.65


def test_cooldown_yeni_kisi_acilmaz() -> None:
    vec = np.ones(16, dtype=np.float32)
    son = [(vec.copy(), 7, 100.0)]
    assert yeni_kisi_acilabilir(vec, son, 110.0, cooldown_sn=30.0) == 7
    assert yeni_kisi_acilabilir(vec, son, 140.0, cooldown_sn=30.0) is None
    diger = np.zeros(16, dtype=np.float32)
    diger[0] = 1.0
    assert yeni_kisi_acilabilir(diger, son, 110.0, cooldown_sn=30.0, cooldown_esik=COOLDOWN_ESIK) is None


def test_kisi_olustur_birlestir_sil(yuz_db) -> None:
    p1 = face_db.kisi_olustur()
    p2 = face_db.kisi_olustur("Ali Veli", is_known=True)
    k1 = face_db.kisi_al(p1)
    assert k1 is not None
    assert k1["name"] == f"Tanımsız Kişi #{p1}"
    assert k1["is_known"] is False
    assert face_db.kisi_al(p2)["is_known"] is True
    v = np.linspace(0, 1, 32, dtype=np.float32)
    face_db.encoding_ekle(p1, v)
    face_db.isim_ver(p1, "Ayşe")
    assert face_db.kisi_al(p1)["is_known"] is True
    face_db.birlestir(p1, p2)
    assert face_db.kisi_al(p1) is None
    mat, ids, adlar, known = face_db.galeri()
    assert p2 in ids
    assert p1 not in ids
    assert any(a == "Ali Veli" for a in adlar)
    face_db.kisi_sil(p2)
    assert face_db.kisi_al(p2) is None
    mat2, ids2, _, _ = face_db.galeri()
    assert mat2.shape[0] == 0
    assert ids2 == []


def test_face_ayri_varsayilan(tmp_path) -> None:
    cfg = ConfigManager(tmp_path / "config.json")
    assert cfg.get("analytics_mode") is None
    assert cfg.get("face_enabled") is False
    assert cfg.get("face_camera_id") == ""
    assert cfg.get("analytics_enabled") is False


def test_sayim_yuz_cakisiyor() -> None:
    from config_manager import sayim_yuz_cakisiyor

    assert sayim_yuz_cakisiyor(True, "a", True, "a") is True
    assert sayim_yuz_cakisiyor(True, "a", True, "b") is False
    assert sayim_yuz_cakisiyor(True, "a", False, "a") is False
    assert sayim_yuz_cakisiyor(False, "a", True, "a") is False


def test_buffalo_det_landmark_degil() -> None:
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1] / "assets" / "insightface" / "buffalo_s"
    if not (kok / "det_500m.onnx").is_file():
        pytest.skip("buffalo_s yok")
    det, rec = buffalo_dosyalari(kok)
    assert det is not None and det.name == "det_500m.onnx"
    assert rec is not None and "w600k" in rec.name.lower()


def test_nms_ust_uste() -> None:
    kutular = np.array(
        [[0.0, 0.0, 10.0, 10.0], [1.0, 1.0, 11.0, 11.0], [50.0, 50.0, 60.0, 60.0]],
        dtype=np.float32,
    )
    skorlar = np.array([0.9, 0.8, 0.7], dtype=np.float32)
    keep = _nms(kutular, skorlar, 0.4)
    assert keep[0] == 0
    assert 2 in keep
    assert 1 not in keep


def test_scrfd_bos_kare() -> None:
    from utils.face_engine import _model_yukle, _yuzleri_al

    model = _model_yukle()
    if model is None:
        pytest.skip("onnxruntime/buffalo yok")
    kare = np.zeros((360, 640, 3), dtype=np.uint8)
    assert _yuzleri_al(model, kare) == []


def test_eski_face_modu_gocer(tmp_path) -> None:
    yol = tmp_path / "config.json"
    yol.write_text(
        '{"analytics_enabled": true, "analytics_camera_id": "cam1", '
        '"analytics_mode": "face", "analytics_fps": 7}',
        encoding="utf-8",
    )
    cfg = ConfigManager(yol)
    assert cfg.get("face_enabled") is True
    assert cfg.get("face_camera_id") == "cam1"
    assert cfg.get("face_fps") == 7
    assert cfg.get("analytics_enabled") is False
    assert "analytics_mode" not in cfg.data


def test_kutu_kaliteli() -> None:
    assert kutu_kaliteli([100, 80, 160, 160], 640, 360, 0.8) is True
    assert kutu_kaliteli([10, 10, 16, 16], 640, 360, 0.9) is False
    assert kutu_kaliteli([100, 80, 160, 160], 640, 360, 0.2) is False
    assert kutu_kaliteli([10, 10, 12, 200], 640, 360, 0.9) is False


def test_encoding_tavani(yuz_db) -> None:
    pid = face_db.kisi_olustur()
    for i in range(5):
        v = np.zeros(8, dtype=np.float32)
        v[0] = 1.0 + i * 0.01
        face_db.encoding_ekle(pid, v, quality=float(i))
    assert face_db.encoding_sayisi(pid) == 3
    face_db.encodings_kirp(pid, 2)
    assert face_db.encoding_sayisi(pid) == 2


def test_benzer_tanimsizlar_birlesir(yuz_db) -> None:
    p1 = face_db.kisi_olustur()
    p2 = face_db.kisi_olustur()
    v = np.zeros(16, dtype=np.float32)
    v[0] = 1.0
    w = v.copy()
    w[1] = 0.05
    face_db.encoding_ekle(p1, v)
    face_db.encoding_ekle(p2, w)
    n = face_db.benzerleri_birlestir(0.50)
    assert n == 1
    kalan = {k["id"] for k in face_db.kisiler()}
    assert kalan == {p1}


def test_ayni_yuz_ikinci_kayit_acmaz(yuz_db, monkeypatch) -> None:
    from utils import face_engine as fe

    vec = np.zeros(32, dtype=np.float32)
    vec[0] = 1.0
    bbox = [100.0, 80.0, 200.0, 200.0]
    damali = np.zeros((120, 120, 3), dtype=np.uint8)
    damali[0:120:2, 0:120:2] = 255
    damali[1:120:2, 1:120:2] = 255

    def fake_yuzler(_model, _frame):
        return [{"bbox": bbox, "embedding": vec, "skor": 0.85, "crop": damali}]

    monkeypatch.setattr(fe, "_yuzleri_al", fake_yuzler)
    monkeypatch.setattr(fe, "kaydedilebilir", lambda *a, **k: True)
    eng = FaceEngine()
    eng._model = ("onnx", None)
    kare = np.zeros((360, 640, 3), dtype=np.uint8)
    for i in range(ENROLL_KARE - 1):
        out = eng.kare_isle(kare, simdi=float(i))
        assert out[0]["person_id"] is None
    out = eng.kare_isle(kare, simdi=float(ENROLL_KARE))
    pid = out[0]["person_id"]
    assert pid is not None
    for i in range(12):
        out = eng.kare_isle(kare, simdi=20.0 + i)
        assert out[0]["person_id"] == pid
    assert len(face_db.kisiler()) == 1
    assert face_db.encoding_sayisi(pid) == 1


def test_kimlik_kilit_yanlis_isme_gecmez() -> None:
    assert kimlik_sec({1: 0.48, 2: 0.51}, kilit_pid=1) == 1
    assert kimlik_sec({1: 0.45, 2: 0.70}, kilit_pid=1) == 2
    assert kimlik_sec({1: 0.56, 2: 0.54}, kilit_pid=None) is None
    assert kimlik_sec({1: 0.70, 2: 0.40}, kilit_pid=None) == 1


def test_kimlik_kayitli_tanimsiza_yenilmez() -> None:
    assert kimlik_sec({10: 0.47, 99: 0.72}, known={10}) == 10
    assert kimlik_sec({10: 0.30, 99: 0.72}, known={10}) != 10


def test_iki_yuz_ayni_ismi_paylasmaz(yuz_db, monkeypatch) -> None:
    from utils import face_engine as fe

    ali = np.zeros(32, dtype=np.float32)
    ali[0] = 1.0
    veli = np.zeros(32, dtype=np.float32)
    veli[1] = 1.0
    p_ali = face_db.kisi_olustur("Ali", is_known=True)
    p_veli = face_db.kisi_olustur("Veli", is_known=True)
    face_db.encoding_ekle(p_ali, ali)
    face_db.encoding_ekle(p_veli, veli)

    def fake(_model, _frame):
        karisik = ali * 0.8 + veli * 0.2
        return [
            {"bbox": [40.0, 40.0, 110.0, 120.0], "embedding": ali, "skor": 0.9},
            {"bbox": [300.0, 40.0, 370.0, 120.0], "embedding": karisik, "skor": 0.7},
        ]

    monkeypatch.setattr(fe, "_yuzleri_al", fake)
    eng = FaceEngine()
    eng._model = ("onnx", None)
    eng.yenile()
    kare = np.zeros((360, 640, 3), dtype=np.uint8)
    out = eng.kare_isle(kare, simdi=0.0)
    ali_say = sum(1 for t in out if t.get("name") == "Ali")
    assert ali_say == 1
    assert all(t.get("name") != "Ali" or t.get("person_id") == p_ali for t in out)


def test_tanimsiz_on_dakika_sonra_silinir(yuz_db) -> None:
    p1 = face_db.kisi_olustur()
    p2 = face_db.kisi_olustur("Ali", is_known=True)
    with face_db._baglan() as bag:
        bag.execute(
            "UPDATE persons SET created_at=? WHERE id=?",
            ("2020-01-01T00:00:00Z", p1),
        )
        bag.commit()
    silinen = face_db.tanimsiz_eski_sil(10)
    assert p1 in silinen
    assert p2 not in silinen
    assert face_db.kisi_al(p1) is None
    assert face_db.kisi_al(p2) is not None


def test_yeni_tanimsiz_hemen_silinmez(yuz_db) -> None:
    p = face_db.kisi_olustur()
    assert face_db.tanimsiz_eski_sil(10) == []
    assert face_db.kisi_al(p) is not None


def test_encoding_kapak_yazilir(yuz_db) -> None:
    from pathlib import Path

    pid = face_db.kisi_olustur()
    crop = np.full((40, 18, 3), (40, 160, 255), dtype=np.uint8)
    face_db.encoding_ekle(pid, np.ones(8, dtype=np.float32), crop)
    kisi = next(k for k in face_db.kisiler() if k["id"] == pid)
    yol = Path(str(kisi["encodings"][0]["image_path"]))
    assert yol.is_file()
    assert yol.stat().st_size > 0
    assert Path(face_db.kisi_kapak_yolu(pid)).is_file()


def test_kaydedilebilir_bulanik_ve_kucuk() -> None:
    from utils.face_quality import kaydedilebilir

    kucuk = np.full((40, 40, 3), 128, dtype=np.uint8)
    assert kaydedilebilir(kucuk, [0, 0, 40, 40]) is False
    bulanik = np.full((100, 100, 3), 128, dtype=np.uint8)
    assert kaydedilebilir(bulanik, [0, 0, 100, 100]) is False
    damali = np.zeros((120, 120, 3), dtype=np.uint8)
    damali[0:120:2, 0:120:2] = 255
    damali[1:120:2, 1:120:2] = 255
    assert kaydedilebilir(damali, [0, 0, 120, 120]) is True


def test_dorduncu_net_foto_en_dusugu_siler(yuz_db) -> None:
    from pathlib import Path

    pid = face_db.kisi_olustur()
    crop = np.zeros((90, 90, 3), dtype=np.uint8)
    for i, q in enumerate((10.0, 20.0, 30.0)):
        v = np.zeros(8, dtype=np.float32)
        v[0] = float(i + 1)
        face_db.encoding_ekle(pid, v, crop, quality=q)
    assert face_db.encoding_sayisi(pid) == 3
    v4 = np.zeros(8, dtype=np.float32)
    v4[0] = 9.0
    face_db.encoding_ekle(pid, v4, crop, quality=5.0)
    assert face_db.encoding_sayisi(pid) == 3
    v5 = np.zeros(8, dtype=np.float32)
    v5[0] = 8.0
    face_db.encoding_ekle(pid, v5, crop, quality=50.0)
    assert face_db.encoding_sayisi(pid) == 3
    with face_db._baglan() as bag:
        skorlar = [
            float(r["quality_score"])
            for r in bag.execute(
                "SELECT quality_score FROM face_encodings WHERE person_id=?",
                (pid,),
            ).fetchall()
        ]
    assert min(skorlar) >= 20.0
    assert 50.0 in skorlar
    klasor = Path(face_db.faces_dir()) / str(pid)
    jpg = list(klasor.glob("*.jpg")) if klasor.is_dir() else []
    assert len(jpg) <= 3


def test_auto_clean_tanimsiz_ve_yetim(yuz_db) -> None:
    from pathlib import Path

    from utils.cleanup import auto_clean_unassigned_faces

    p1 = face_db.kisi_olustur()
    p2 = face_db.kisi_olustur("Ali", is_known=True)
    crop = np.zeros((80, 80, 3), dtype=np.uint8)
    crop[::2, ::2] = 255
    face_db.encoding_ekle(p1, np.ones(8, dtype=np.float32), crop, quality=200)
    face_db.encoding_ekle(p2, np.ones(8, dtype=np.float32), crop, quality=200)
    yetim = Path(face_db.faces_dir()) / "yetim.jpg"
    yetim.parent.mkdir(parents=True, exist_ok=True)
    yetim.write_bytes(b"x")
    with face_db._baglan() as bag:
        bag.execute(
            "UPDATE persons SET created_at=? WHERE id=?",
            ("2020-01-01T00:00:00Z", p1),
        )
        bag.commit()
    silinen = auto_clean_unassigned_faces(10)
    assert p1 in silinen
    assert face_db.kisi_al(p1) is None
    assert face_db.kisi_al(p2) is not None
    assert not yetim.is_file()


def test_birlestir_en_fazla_uc_encoding(yuz_db) -> None:
    p1 = face_db.kisi_olustur()
    p2 = face_db.kisi_olustur("Ali", is_known=True)
    crop = np.zeros((80, 80, 3), dtype=np.uint8)
    for i in range(3):
        v = np.zeros(8, dtype=np.float32)
        v[0] = float(i + 1)
        face_db.encoding_ekle(p1, v, crop, quality=float(i))
    for i in range(2):
        v = np.zeros(8, dtype=np.float32)
        v[0] = float(i + 10)
        face_db.encoding_ekle(p2, v, crop, quality=float(10 + i))
    face_db.birlestir(p1, p2)
    assert face_db.kisi_al(p1) is None
    assert face_db.encoding_sayisi(p2) == 3


def test_yuz_disa_ice_aktar(yuz_db, tmp_path) -> None:
    from pathlib import Path

    from utils.face_transfer import disa_aktar, ice_aktar

    pid = face_db.kisi_olustur("Serkan Mercan", is_known=True)
    crop = np.zeros((90, 90, 3), dtype=np.uint8)
    crop[::2, ::2] = 255
    face_db.encoding_ekle(pid, np.ones(16, dtype=np.float32), crop, quality=200)
    zip_yol = tmp_path / "yuzler.zip"
    disa_aktar(zip_yol)
    assert zip_yol.is_file()
    face_db.kisi_sil(pid)
    assert face_db.kisi_al(pid) is None
    n = ice_aktar(zip_yol)
    assert n >= 1
    gelen = [k for k in face_db.kisiler() if k["name"] == "Serkan Mercan"]
    assert gelen
    kapak = face_db.kisi_kapak_yolu(int(gelen[0]["id"]))
    assert kapak and Path(kapak).is_file()
