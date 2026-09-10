"""
KobiCAM 1.2.0 stres / birim testleri.

Gerçek kamera veya Google hesabı gerekmez.
Çalıştırma: pip install pytest httpx psutil && python -m pytest tests -q
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from analytics_worker import cizgi_kesisi, dwell_hesap, kaybolan_dwell
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
