"""AES-GCM, ENC: göç, kurtarma kodu."""

from __future__ import annotations

from pathlib import Path

from auth_manager import AuthManager, uret_kurtarma_kodu
from security.crypto_manager import (
    decrypt_string,
    encrypt_string,
    gocet_duz_metin,
    sifrele_url,
)


def test_encrypt_decrypt_roundtrip() -> None:
    duz = "gizli-parola-üöş"
    sifreli = encrypt_string(duz)
    assert sifreli.startswith("ENC:")
    assert decrypt_string(sifreli) == duz
    assert encrypt_string(sifreli) == sifreli
    assert encrypt_string("") == ""


def test_sifrele_url_userinfo() -> None:
    url = "rtsp://admin:sifre@10.0.0.5/stream"
    cikti = sifrele_url(url)
    assert cikti.startswith("ENC:")
    assert decrypt_string(cikti) == url
    acik = "rtsp://10.0.0.5/stream1"
    assert sifrele_url(acik) == acik


def test_gocet_duz_metin() -> None:
    veri = {
        "gdrive_oauth_client_secret": "sekret",
        "devices": [{"password": "dvrpass"}],
        "cameras": [
            {
                "password": "cam",
                "main_url": "rtsp://u:p@1.1.1.1/main",
                "sub_url": "rtsp://1.1.1.1/sub",
            }
        ],
    }
    assert gocet_duz_metin(veri) is True
    assert str(veri["gdrive_oauth_client_secret"]).startswith("ENC:")
    assert str(veri["devices"][0]["password"]).startswith("ENC:")
    assert str(veri["cameras"][0]["main_url"]).startswith("ENC:")
    assert veri["cameras"][0]["sub_url"] == "rtsp://1.1.1.1/sub"
    assert gocet_duz_metin(veri) is False


def test_config_kayit_enc(tmp_path: Path) -> None:
    from config_manager import ConfigManager

    yol = tmp_path / "config.json"
    cfg = ConfigManager(yol)
    cfg.set(
        "cameras",
        [{"id": "1", "password": "x", "main_url": "rtsp://a:b@10.0.0.1/s", "sub_url": ""}],
        kaydet=True,
    )
    ham = yol.read_text(encoding="utf-8")
    assert "ENC:" in ham
    assert "rtsp://a:b@" not in ham
    tekrar = ConfigManager(yol)
    kam = tekrar.cameras()[0]
    assert kam["password"] == "x"
    assert "a:b@" in kam["main_url"]


def test_kurtarma_kodu(tmp_path: Path) -> None:
    auth = AuthManager(tmp_path / "users.db")
    auth.create_user("operator1", "GucluSifre9")
    kod = uret_kurtarma_kodu()
    auth.kaydet_kurtarma_kodu(kod)
    auth.sifre_sifirla(kod, "YeniSifre88", "operator1")
    assert auth.authenticate("operator1", "YeniSifre88") == "operator1"
