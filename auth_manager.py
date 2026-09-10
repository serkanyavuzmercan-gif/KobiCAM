"""
Kullanıcı kimlik doğrulama ve ilk kurulum yönetimi.

- İlk çalıştırmada kullanıcı tablosu boştur (Clean Installation).
- Ana hesap PBKDF2-HMAC-SHA256 (600_000 tur, 32-byte tuz) ile saklanır.
- Gömülü yedek admin yoktur; kurtarma kodu kurulumda bir kez üretilir.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import secrets
from datetime import datetime, timezone
from pathlib import Path

from db_util import baglan


APP_NAME = "KobiCAM"

PBKDF2_ITERATIONS = 600_000
PBKDF2_ESKI_TUR = 200_000
PBKDF2_HASH_NAME = "sha256"
SALT_LEN = 32
SALT_ESKI = 16

MIN_USERNAME_LEN = 3
MAX_USERNAME_LEN = 32
MIN_PASSWORD_LEN = 8


def get_app_data_dir() -> Path:
    """İşletim sistemine uygun uygulama veri klasörünü döndürür ve oluşturur."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    klasor = base / APP_NAME
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_password(
    password: str,
    salt: bytes | None = None,
    iterations: int | None = None,
) -> tuple[bytes, bytes]:
    """PBKDF2-HMAC-SHA256. Tur varsayılanı PBKDF2_ITERATIONS."""
    if salt is None:
        salt = secrets.token_bytes(SALT_LEN)
    tur = int(iterations or PBKDF2_ITERATIONS)
    ozet = hashlib.pbkdf2_hmac(
        PBKDF2_HASH_NAME,
        password.encode("utf-8"),
        salt,
        tur,
    )
    return salt, ozet


def verify_password(
    password: str,
    salt: bytes,
    expected_hash: bytes,
    iterations: int | None = None,
) -> bool:
    tur = iterations
    if tur is None:
        tur = PBKDF2_ESKI_TUR if len(salt) == SALT_ESKI else PBKDF2_ITERATIONS
    _, ozet = hash_password(password, salt=salt, iterations=tur)
    return hmac.compare_digest(ozet, expected_hash)


def normalize_kurtarma_kodu(kod: str) -> str:
    return "".join(c for c in (kod or "").upper() if c.isalnum())


def uret_kurtarma_kodu() -> str:
    """256-bit, dört karakterlik gruplar (XXXX-XXXX-...)."""
    hexstr = secrets.token_bytes(32).hex().upper()
    return "-".join(hexstr[i : i + 4] for i in range(0, len(hexstr), 4))


class AuthError(Exception):
    """Kimlik doğrulama / kullanıcı işlemleri için uygulama hatası."""


class AuthManager:
    """SQLite kullanıcı deposu ve kurulum kurtarma kodu."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else get_app_data_dir() / "users.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return baglan(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as baglanti:
            baglanti.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                    salt          BLOB    NOT NULL,
                    password_hash BLOB    NOT NULL,
                    created_at    TEXT    NOT NULL
                )
                """
            )
            baglanti.execute(
                """
                CREATE TABLE IF NOT EXISTS recovery (
                    id         INTEGER PRIMARY KEY CHECK (id = 1),
                    salt       BLOB NOT NULL,
                    code_hash  BLOB NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            baglanti.commit()

    def is_first_run(self) -> bool:
        return self.user_count() == 0

    def user_count(self) -> int:
        with self._connect() as baglanti:
            satir = baglanti.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            return int(satir["n"]) if satir else 0

    def validate_username(self, username: str) -> str:
        ad = (username or "").strip()
        if len(ad) < MIN_USERNAME_LEN or len(ad) > MAX_USERNAME_LEN:
            raise AuthError(
                f"Kullanıcı adı {MIN_USERNAME_LEN}–{MAX_USERNAME_LEN} karakter olmalıdır."
            )
        if not ad.replace("_", "").isalnum():
            raise AuthError(
                "Kullanıcı adı yalnızca harf, rakam ve alt çizgi içerebilir."
            )
        return ad

    def validate_password(self, password: str) -> None:
        if not password or len(password) < MIN_PASSWORD_LEN:
            raise AuthError(f"Şifre en az {MIN_PASSWORD_LEN} karakter olmalıdır.")

    def create_user(self, username: str, password: str) -> str:
        ad = self.validate_username(username)
        self.validate_password(password)
        tuz, ozet = hash_password(password)
        try:
            with self._connect() as baglanti:
                baglanti.execute(
                    """
                    INSERT INTO users (username, salt, password_hash, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (ad, tuz, ozet, _utc_now_iso()),
                )
                baglanti.commit()
        except sqlite3.IntegrityError as exc:
            raise AuthError("Bu kullanıcı adı zaten kayıtlı.") from exc
        return ad

    def kaydet_kurtarma_kodu(self, kod: str) -> None:
        ham = normalize_kurtarma_kodu(kod)
        if len(ham) < 32:
            raise AuthError("Kurtarma kodu geçersiz.")
        tuz, ozet = hash_password(ham)
        with self._connect() as baglanti:
            baglanti.execute("DELETE FROM recovery")
            baglanti.execute(
                "INSERT INTO recovery (id, salt, code_hash, created_at) VALUES (1, ?, ?, ?)",
                (tuz, ozet, _utc_now_iso()),
            )
            baglanti.commit()

    def authenticate(self, username: str, password: str) -> str:
        ad = (username or "").strip()
        if not ad or password is None:
            raise AuthError("Kullanıcı adı ve şifre zorunludur.")

        with self._connect() as baglanti:
            satir = baglanti.execute(
                "SELECT username, salt, password_hash FROM users WHERE username = ? COLLATE NOCASE",
                (ad,),
            ).fetchone()

        if satir is None:
            raise AuthError("Kullanıcı adı veya şifre hatalı.")

        tuz = bytes(satir["salt"])
        ozet = bytes(satir["password_hash"])
        if not verify_password(password, tuz, ozet):
            raise AuthError("Kullanıcı adı veya şifre hatalı.")

        if len(tuz) != SALT_LEN:
            yeni_tuz, yeni_ozet = hash_password(password)
            with self._connect() as baglanti:
                baglanti.execute(
                    "UPDATE users SET salt=?, password_hash=? WHERE username=? COLLATE NOCASE",
                    (yeni_tuz, yeni_ozet, ad),
                )
                baglanti.commit()

        return str(satir["username"])

    def sifre_sifirla(self, kod: str, yeni_sifre: str, username: str) -> str:
        """Kurtarma kodu ile kullanıcının parolasını değiştirir."""
        ad = self.validate_username(username)
        self.validate_password(yeni_sifre)
        ham = normalize_kurtarma_kodu(kod)
        with self._connect() as baglanti:
            rec = baglanti.execute(
                "SELECT salt, code_hash FROM recovery WHERE id=1"
            ).fetchone()
            kullanici = baglanti.execute(
                "SELECT username FROM users WHERE username=? COLLATE NOCASE",
                (ad,),
            ).fetchone()
        if rec is None or kullanici is None:
            raise AuthError("Kurtarma kodu veya kullanıcı geçersiz.")
        if not verify_password(ham, bytes(rec["salt"]), bytes(rec["code_hash"])):
            raise AuthError("Kurtarma kodu veya kullanıcı geçersiz.")
        tuz, ozet = hash_password(yeni_sifre)
        with self._connect() as baglanti:
            baglanti.execute(
                "UPDATE users SET salt=?, password_hash=? WHERE username=? COLLATE NOCASE",
                (tuz, ozet, ad),
            )
            baglanti.commit()
        return str(kullanici["username"])
