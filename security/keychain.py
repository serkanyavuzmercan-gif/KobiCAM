"""Windows Credential Manager / DPAPI Master Key (32 byte)."""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

_SERVIS = "KobiCAM"
_HESAP = "master-aes-256"
_ANAHTAR_BOY = 32
_onbellek: bytes | None = None


class KeychainError(Exception):
    """Master Key okunamadı / yazılamadı."""


def _appdata() -> Path:
    from auth_manager import get_app_data_dir

    return get_app_data_dir()


def _dpapi_yol() -> Path:
    return _appdata() / "master.key.dpapi"


def _dpapi_koru(düz: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(düz, len(düz))
    giris = DATA_BLOB(len(düz), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    cikis = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(giris), None, None, None, None, 0, ctypes.byref(cikis)
    ):
        raise KeychainError("CryptProtectData başarısız")
    try:
        return ctypes.string_at(cikis.pbData, cikis.cbData)
    finally:
        kernel32.LocalFree(cikis.pbData)


def _dpapi_coz(sifreli: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(sifreli, len(sifreli))
    giris = DATA_BLOB(len(sifreli), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    cikis = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(giris), None, None, None, None, 0, ctypes.byref(cikis)
    ):
        raise KeychainError("CryptUnprotectData başarısız")
    try:
        return ctypes.string_at(cikis.pbData, cikis.cbData)
    finally:
        kernel32.LocalFree(cikis.pbData)


def _keyring_oku() -> bytes | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        ham = keyring.get_password(_SERVIS, _HESAP)
    except Exception:
        return None
    if not ham:
        return None
    try:
        anahtar = base64.b64decode(ham.encode("ascii"))
    except Exception:
        return None
    return anahtar if len(anahtar) == _ANAHTAR_BOY else None


def _keyring_yaz(anahtar: bytes) -> bool:
    try:
        import keyring

        keyring.set_password(_SERVIS, _HESAP, base64.b64encode(anahtar).decode("ascii"))
        return True
    except Exception:
        return False


def _dpapi_oku() -> bytes | None:
    yol = _dpapi_yol()
    if not yol.is_file() or os.name != "nt":
        return None
    try:
        anahtar = _dpapi_coz(yol.read_bytes())
    except Exception:
        return None
    return anahtar if len(anahtar) == _ANAHTAR_BOY else None


def _dpapi_yaz(anahtar: bytes) -> bool:
    if os.name != "nt":
        return False
    try:
        yol = _dpapi_yol()
        yol.write_bytes(_dpapi_koru(anahtar))
        try:
            yol.chmod(0o600)
        except OSError:
            pass
        return True
    except Exception:
        return False


def master_key() -> bytes:
    """
    256-bit uygulama anahtarı.

    Öncelik: test ortam değişkeni, bellek, Credential Manager, DPAPI dosyası,
    yoksa üretilir.
    """
    global _onbellek
    if _onbellek is not None:
        return _onbellek
    test = (os.environ.get("KOBICAM_TEST_MASTER_KEY") or "").strip()
    if len(test) == 64:
        try:
            _onbellek = bytes.fromhex(test)
            return _onbellek
        except ValueError:
            pass
    for okuyucu in (_keyring_oku, _dpapi_oku):
        bulunan = okuyucu()
        if bulunan:
            _onbellek = bulunan
            return _onbellek
    anahtar = secrets.token_bytes(_ANAHTAR_BOY)
    if not _keyring_yaz(anahtar) and not _dpapi_yaz(anahtar):
        raise KeychainError(
            "Master Key Windows Credential Manager veya DPAPI ile saklanamadı."
        )
    _onbellek = anahtar
    return anahtar
