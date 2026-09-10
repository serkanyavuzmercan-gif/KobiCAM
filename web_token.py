"""Web oturumu için HS256 JWT (PyJWT). Süreç belleğinde, diske yazılmaz."""

from __future__ import annotations

import secrets
import time
from typing import Any

from auth_manager import get_app_data_dir

_ALG = "HS256"
_TTL_SN = 12 * 3600
_gizli: str | None = None


def _eski_dosyalari_sil() -> None:
    yol = get_app_data_dir() / "web_jwt_secret.txt"
    if yol.is_file():
        try:
            yol.unlink()
        except OSError:
            pass


def jwt_gizli(config: Any = None) -> str:
    """Her süreçte bir kez üretilir; config.json kullanılmaz."""
    global _gizli
    if _gizli:
        return _gizli
    _eski_dosyalari_sil()
    if config is not None:
        try:
            config.set("web_jwt_secret", "", kaydet=False)
        except Exception:
            pass
    _gizli = secrets.token_urlsafe(32)
    return _gizli


def jeton_olustur(kullanici: str, gizli: str) -> str:
    import jwt

    govde = {"sub": kullanici, "exp": int(time.time()) + _TTL_SN}
    return jwt.encode(govde, gizli, algorithm=_ALG)


def jeton_dogrula(jeton: str, gizli: str) -> str | None:
    import jwt

    try:
        govde = jwt.decode(jeton or "", gizli, algorithms=[_ALG])
    except Exception:
        return None
    ad = str(govde.get("sub") or "").strip()
    return ad or None
