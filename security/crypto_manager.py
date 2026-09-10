"""AES-256-GCM dize şifreleme; config.json için ENC: öneki."""

from __future__ import annotations

import base64
import secrets
from typing import Any
from urllib.parse import urlparse

_ONEK = "ENC:"
_NONCE = 12


class CryptoError(Exception):
    """Şifreleme / çözme hatası (geçersiz MAC dahil)."""


def _aes() -> Any:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from security.keychain import master_key

    return AESGCM(master_key())


def encrypt_string(plain_text: str) -> str:
    """Boş dize olduğu gibi; ENC: ile başlayan tekrar şifrelenmez."""
    metin = plain_text if isinstance(plain_text, str) else str(plain_text or "")
    if not metin:
        return metin
    if metin.startswith(_ONEK):
        return metin
    nonce = secrets.token_bytes(_NONCE)
    try:
        ct = _aes().encrypt(nonce, metin.encode("utf-8"), None)
    except Exception as hata:
        raise CryptoError(str(hata)) from hata
    return _ONEK + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_string(cipher_text: str) -> str:
    """ENC: değilse düz metin kabul edilir (göç). MAC hatası CryptoError."""
    metin = cipher_text if isinstance(cipher_text, str) else str(cipher_text or "")
    if not metin or not metin.startswith(_ONEK):
        return metin
    try:
        ham = base64.b64decode(metin[len(_ONEK) :].encode("ascii"))
        nonce, ct = ham[:_NONCE], ham[_NONCE:]
        return _aes().decrypt(nonce, ct, None).decode("utf-8")
    except CryptoError:
        raise
    except Exception as hata:
        raise CryptoError("Sır çözülemedi") from hata


def _url_hassas(url: str) -> bool:
    if not url or url.startswith(_ONEK):
        return False
    if "password=" in url.lower():
        return True
    try:
        p = urlparse(url)
    except Exception:
        return False
    return bool(p.username or p.password)


def sifrele_url(url: str) -> str:
    """user:pass@ veya password= içeren URL’nin tamamını şifreler."""
    if not url or url.startswith(_ONEK):
        return url
    if _url_hassas(url):
        return encrypt_string(url)
    return url


def _alan_sifrele(deger: Any, url_mu: bool) -> tuple[Any, bool]:
    if not isinstance(deger, str) or not deger:
        return deger, False
    if deger.startswith(_ONEK):
        return deger, False
    if url_mu:
        if not _url_hassas(deger):
            return deger, False
        return encrypt_string(deger), True
    return encrypt_string(deger), True


def gocet_duz_metin(veri: dict[str, Any]) -> bool:
    """Düz metin sırları ENC: yapar. Değişiklik olduysa True."""
    degisti = False
    for anahtar in ("gdrive_oauth_client_secret", "ngrok_authtoken"):
        yeni, oldu = _alan_sifrele(veri.get(anahtar) or "", False)
        if oldu:
            veri[anahtar] = yeni
            degisti = True
    for liste_adi in ("devices", "cameras"):
        ogeler = veri.get(liste_adi)
        if not isinstance(ogeler, list):
            continue
        for oge in ogeler:
            if not isinstance(oge, dict):
                continue
            yeni, oldu = _alan_sifrele(oge.get("password") or "", False)
            if oldu:
                oge["password"] = yeni
                degisti = True
            if liste_adi == "cameras":
                for url_k in ("main_url", "sub_url"):
                    yeni, oldu = _alan_sifrele(oge.get(url_k) or "", True)
                    if oldu:
                        oge[url_k] = yeni
                        degisti = True
    return degisti


def bellege_coz(veri: dict[str, Any]) -> None:
    """ENC: alanlarını bellekte düz metne çevirir. MAC hatası yutulmaz, boşaltılır."""
    for anahtar in ("gdrive_oauth_client_secret", "ngrok_authtoken"):
        ham = veri.get(anahtar)
        if isinstance(ham, str) and ham.startswith(_ONEK):
            try:
                veri[anahtar] = decrypt_string(ham)
            except CryptoError:
                veri[anahtar] = ""
    for liste_adi in ("devices", "cameras"):
        ogeler = veri.get(liste_adi)
        if not isinstance(ogeler, list):
            continue
        for oge in ogeler:
            if not isinstance(oge, dict):
                continue
            ham = oge.get("password")
            if isinstance(ham, str) and ham.startswith(_ONEK):
                try:
                    oge["password"] = decrypt_string(ham)
                except CryptoError:
                    oge["password"] = ""
            if liste_adi == "cameras":
                for url_k in ("main_url", "sub_url"):
                    ham = oge.get(url_k)
                    if isinstance(ham, str) and ham.startswith(_ONEK):
                        try:
                            oge[url_k] = decrypt_string(ham)
                        except CryptoError:
                            oge[url_k] = ""


def disk_icin_sifrele(veri: dict[str, Any]) -> dict[str, Any]:
    """Kopyayı şifreler; kaynak sözlük değişmez."""
    from copy import deepcopy

    kopya = deepcopy(veri)
    gocet_duz_metin(kopya)
    kopya["web_jwt_secret"] = ""
    return kopya
