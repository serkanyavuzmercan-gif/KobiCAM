"""
KobiCAM 1.3.1 stres / birim testleri.

Gerçek kamera veya Google hesabı gerekmez.
Çalıştırma: pip install pytest httpx psutil && python -m pytest tests -q
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from analytics_worker import (
    AnalyticsWorker,
    analitik_csv_yaz,
    cizgi_kesisi,
    dwell_hesap,
    grafik_y_ust,
    kaybolan_dwell,
    kesenleri_uygula,
    rapor_grupla,
    saat_etiketi_yerel,
    sayim_karar,
    yerel_utc_parantez,
)
from gdrive_sync import backoff_saniye, silinecek_drive_dosyalari


def test_drive_retention_5_gun() -> None:
    simdi = datetime.now(timezone.utc)
    eski = (simdi - timedelta(hours=130)).strftime("%Y-%m-%dT%H:%M:%SZ")
    yeni = (simdi - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    esik = simdi.timestamp() - 120 * 3600
    silinecek = silinecek_drive_dosyalari(
        [
            {"id": "eski1", "createdTime": eski},
            {"id": "yeni1", "createdTime": yeni},
            {"id": "bozuk", "createdTime": "degil-tarih"},
        ],
        esik,
    )
    assert silinecek == ["eski1"]


def test_drive_backoff_ustel() -> None:
    assert backoff_saniye(0) == 15
    assert backoff_saniye(1) == 30
    assert backoff_saniye(8) == 3600
    assert backoff_saniye(20) == 3600


def test_sayim_cizgisi_in_out() -> None:
    cizgi = [0.0, 0.5, 1.0, 0.5]
    assert cizgi_kesisi(cizgi, (0.5, 0.8), (0.5, 0.2)) == "out"
    assert cizgi_kesisi(cizgi, (0.5, 0.2), (0.5, 0.8)) == "in"
    assert cizgi_kesisi(cizgi, (0.2, 0.2), (0.8, 0.2)) is None


def test_sayim_dikey_cizgi_kapi() -> None:
    cizgi = [0.4, 0.0, 0.4, 1.0]
    assert cizgi_kesisi(cizgi, (0.7, 0.5), (0.2, 0.5)) == "in"
    assert cizgi_kesisi(cizgi, (0.2, 0.5), (0.7, 0.5)) == "out"


def test_kesenleri_uygula_ilk_konum_saymaz() -> None:
    konum: dict[int, tuple[float, float]] = {}
    cizgi = [0.5, 0.0, 0.5, 1.0]
    assert kesenleri_uygula(cizgi, konum, 1, (0.8, 0.5)) is None
    assert kesenleri_uygula(cizgi, konum, 1, (0.2, 0.5)) == "in"
    assert kesenleri_uygula(cizgi, konum, 1, (0.8, 0.5)) == "out"


def test_kesenleri_cizgi_uzerinde_tarafi_korur() -> None:
    konum: dict[int, tuple[float, float]] = {}
    cizgi = [0.5, 0.0, 0.5, 1.0]
    assert kesenleri_uygula(cizgi, konum, 1, (0.8, 0.5)) is None
    assert kesenleri_uygula(cizgi, konum, 1, (0.5, 0.5)) is None
    assert konum[1] == (0.8, 0.5)
    assert kesenleri_uygula(cizgi, konum, 1, (0.2, 0.5)) == "in"


def test_kutu_ayak_nokta() -> None:
    from analytics_worker import kutu_ayak_nokta

    cx, cy = kutu_ayak_nokta([10.0, 20.0, 50.0, 180.0], 640, 360)
    assert cx == pytest.approx(30.0 / 640)
    assert cy == pytest.approx(180.0 / 360)


def test_sayim_karar_tekrar_giris() -> None:
    durum: dict[int, dict] = {}
    assert sayim_karar(1, "in", 0.0, durum, 15) == "in"
    assert sayim_karar(1, "out", 2.0, durum, 15) is None
    assert sayim_karar(1, "out", 20.0, durum, 15) == "out"
    assert sayim_karar(1, "in", 40.0, durum, 15) == "reentry"
    assert sayim_karar(1, "in", 60.0, durum, 15) is None


def test_analitik_csv_yaz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "analytics_worker.olaylari_al",
        lambda _kid: [
            ("2026-09-11T08:00:00Z", "in", 7, None),
            ("2026-09-11T08:05:00Z", "reentry", 7, None),
            ("2026-09-11T08:10:00Z", "out", 7, None),
            ("2026-09-11T08:10:00Z", "dwell", 7, 12.5),
        ],
    )
    monkeypatch.setattr(
        "analytics_worker.saatlik_bugun",
        lambda _kid: [("2026-09-11T08:00:00Z", 1, 1, 12.5)],
    )
    yol = tmp_path / "analitik.csv"
    n = analitik_csv_yaz(yol, "cam1", "Ofis")
    assert n == 4
    metin = yol.read_text(encoding="utf-8-sig")
    assert "Tekrar giren" in metin
    assert "Giren" in metin
    assert "Çıkan" in metin
    assert ";" in metin
    assert "Saatlik ozet" in metin
    assert "Haftalik rapor" in metin
    assert "Aylik rapor" in metin
    assert "Gunluk ozet" in metin
    assert "Olay detayi" in metin


def test_rapor_grupla_hafta_ay() -> None:
    olaylar = [
        ("2026-09-07T08:00:00Z", "in", 1, None),
        ("2026-09-07T09:00:00Z", "out", 1, None),
        ("2026-09-07T09:00:00Z", "dwell", 1, 20.0),
        ("2026-09-14T08:00:00Z", "in", 2, None),
        ("2026-09-14T08:30:00Z", "reentry", 2, None),
    ]
    r = rapor_grupla(olaylar)
    assert r["genel"]["giren"] == 2
    assert r["genel"]["cikan"] == 1
    assert r["genel"]["tekrar"] == 1
    assert len(r["haftalik"]) >= 1
    assert len(r["aylik"]) == 1
    ay = next(iter(r["aylik"].values()))
    assert "2026" in str(ay.get("etiket", ""))


def test_grafik_y_ust_buyur() -> None:
    assert grafik_y_ust(0) == 5
    assert grafik_y_ust(1) == 5
    assert grafik_y_ust(5) == 5
    assert grafik_y_ust(6) == 10
    assert grafik_y_ust(47) == 50
    assert grafik_y_ust(120) == 150


def test_saat_etiketi_yerel_utc() -> None:
    dt = datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)
    yerel = dt.astimezone()
    assert saat_etiketi_yerel("2026-09-11T08:00:00Z") == f"{yerel.hour:02d}"
    assert yerel_utc_parantez().startswith("UTC")


def test_kareye_cizgi_boyut_korunur() -> None:
    import numpy as np
    from analytics_worker import kareye_cizgi

    kare = np.zeros((360, 640, 3), dtype=np.uint8)
    kutular = np.array([[10.0, 20.0, 40.0, 80.0]])
    cizili = kareye_cizgi(kare, [0.2, 0.1, 0.2, 0.9], 3, 1, kutular)
    assert cizili.shape == kare.shape
    assert not np.array_equal(cizili, kare)


def test_analytics_cizgi_sonradan_verilir() -> None:
    """Önizleme çizgisiz başlar; sayım çizgisi sonradan takılır."""
    from PyQt6.QtCore import QCoreApplication
    import sys

    QCoreApplication.instance() or QCoreApplication(sys.argv)
    isci = AnalyticsWorker({"id": "c1", "sub_url": "rtsp://ornek"}, [], 5)
    assert isci._cizgi == []
    isci.set_cizgi([0.1, 0.2, 0.8, 0.9, 1.0])
    assert isci._cizgi == [0.1, 0.2, 0.8, 0.9]


def test_dwell_matematik() -> None:
    assert dwell_hesap(0.0, 0.4) is None
    assert dwell_hesap(10.0, 15.0) == pytest.approx(5.0)
    ilk = {7: 1.0, 8: 2.0}
    sonuc = kaybolan_dwell(ilk, {8}, 6.0)
    assert len(sonuc) == 1
    assert sonuc[0][0] == 7
    assert sonuc[0][1] == pytest.approx(5.0)
    assert 7 not in ilk
    assert 8 in ilk


def _web_istemci(tmp_path: Path):
    from auth_manager import AuthManager
    from config_manager import ConfigManager
    from web_server import _uygulama, web_ortam_ayarla
    from web_token import jeton_olustur

    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi yok")

    cfg = ConfigManager(tmp_path / "config.json")
    cfg.set(
        "cameras",
        [
            {
                "id": "cam1",
                "name": "Ofis",
                "main_url": "rtsp://gizli:sifre@10.0.0.9/stream",
                "sub_url": "rtsp://gizli:sifre@10.0.0.9/sub",
            }
        ],
        kaydet=True,
    )
    auth = AuthManager(tmp_path / "users.db")
    auth.create_user("operator1", "GucluSifre9")
    gizli = "test-jwt-secret-kobicam-qa-hardening-32b"
    web_ortam_ayarla(cfg, auth, gizli)
    return TestClient(_uygulama()), gizli, jeton_olustur


def test_fastapi_login_jwt_hls(tmp_path: Path) -> None:
    istemci, gizli, jeton_olustur = _web_istemci(tmp_path)

    r = istemci.post("/api/login", json={"username": "operator1", "password": "yanlis"})
    assert r.status_code == 401

    r = istemci.post("/api/login", json={"username": "operator1", "password": "GucluSifre9"})
    assert r.status_code == 200
    govde = r.json()
    assert govde.get("ok") is True
    token = govde["token"]
    assert jeton_olustur("operator1", gizli)

    r = istemci.get("/api/me")
    assert r.status_code == 200

    r = istemci.get("/api/health")
    assert r.status_code == 200
    saglik = r.json()
    assert saglik.get("ok") is True
    assert saglik.get("yayin") is True
    assert "port" in saglik

    r = istemci.get("/api/cameras")
    assert r.status_code == 200
    kameralar = r.json()
    assert kameralar[0]["id"] == "cam1"
    metin = json.dumps(kameralar)
    assert "rtsp://" not in metin
    assert "gizli" not in metin

    from fastapi.testclient import TestClient
    from auth_manager import AuthManager
    from config_manager import ConfigManager
    from web_server import _uygulama, web_ortam_ayarla

    web_ortam_ayarla(
        ConfigManager(tmp_path / "config.json"),
        AuthManager(tmp_path / "users.db"),
        gizli,
    )
    cirak = TestClient(_uygulama())
    r = cirak.get("/hls/cam1/index.m3u8")
    assert r.status_code == 401
    r = cirak.get("/api/cameras", headers={"Authorization": "Bearer sagir-jeton"})
    assert r.status_code == 401


def test_fastapi_es_zamanli_login(tmp_path: Path) -> None:
    istemci, _, _ = _web_istemci(tmp_path)

    def bir(_i: int) -> int:
        cevap = istemci.post(
            "/api/login",
            json={"username": "operator1", "password": "GucluSifre9"},
        )
        return cevap.status_code

    with ThreadPoolExecutor(max_workers=12) as havuz:
        kodlar = [f.result() for f in as_completed(havuz.submit(bir, i) for i in range(12))]
    assert kodlar.count(200) == 12
