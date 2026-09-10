"""Rotating dosya günlüğü: %APPDATA%\\KobiCAM\\logs\\kobicam.log"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_KURULDU = False
_LOGGER: logging.Logger | None = None

_KALIPLAR: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(password\s*[=:]\s*)([^\s&;'\"]+)", re.I), r"\1****"),
    (re.compile(r"(passwd\s*[=:]\s*)([^\s&;'\"]+)", re.I), r"\1****"),
    (re.compile(r"(client_secret\s*[=:]\s*)([^\s&;'\"]+)", re.I), r"\1****"),
    (re.compile(r"(authtoken\s*[=:]\s*)([^\s&;'\"]+)", re.I), r"\1****"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I), r"\1****"),
    (re.compile(r"ENC:[A-Za-z0-9+/=]+"), "ENC:****"),
    (re.compile(r"(://[^:/@\s]+):([^@/\s]+)@"), r"\1:****@"),
)


class RedactingFormatter(logging.Formatter):
    """Şifre, RTSP userinfo, ENC: ve Bearer jetonlarını maskeler."""

    def format(self, record: logging.LogRecord) -> str:
        metin = super().format(record)
        for kalip, yer in _KALIPLAR:
            metin = kalip.sub(yer, metin)
        return metin


def log_klasoru() -> Path:
    from auth_manager import get_app_data_dir

    yol = get_app_data_dir() / "logs"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def log_yolu() -> Path:
    return log_klasoru() / "kobicam.log"


def _kur() -> logging.Logger:
    global _KURULDU, _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logger = logging.getLogger("kobicam")
    logger.setLevel(logging.INFO)
    bicim = RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if not _KURULDU:
        try:
            isleyici = RotatingFileHandler(
                str(log_yolu()),
                maxBytes=2 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            isleyici.setFormatter(bicim)
            logger.addHandler(isleyici)
        except OSError:
            hata = logging.StreamHandler(sys.stderr)
            hata.setFormatter(bicim)
            logger.addHandler(hata)
        logger.propagate = False
        _KURULDU = True
    _LOGGER = logger
    return logger


def get_logger(ek: str = "") -> logging.Logger:
    kok = _kur()
    if ek:
        return kok.getChild(ek)
    return kok


def yakalanmamis_kaydet(tur, deger, iz) -> None:
    get_logger("crash").error("Yakalanmamış hata", exc_info=(tur, deger, iz))
