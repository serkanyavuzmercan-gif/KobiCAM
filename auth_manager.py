"""
Kullanıcı kimlik doğrulama ve ilk kurulum yönetimi.

- İlk çalıştırmada kullanıcı tablosu boştur (Clean Installation).
- Ana hesap PBKDF2-HMAC-SHA256 ile hash'lenerek SQLite'da saklanır.
- 'admin' hesabı kod içine gömülü hash ile her zaman geçerlidir; UI'dan değiştirilemez.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import secrets
from datetime import datetime, timezone
from pathlib import Path


APP_NAME = "KobiCAM"

# PBKDF2 parametreleri — brute-force'a karşı yüksek iterasyon
PBKDF2_ITERATIONS = 200_000
PBKDF2_HASH_NAME = "sha256"
SALT_LEN = 16

# Kullanıcı adı / şifre kuralları
MIN_USERNAME_LEN = 3
MAX_USERNAME_LEN = 32
MIN_PASSWORD_LEN = 8

# ---------------------------------------------------------------------------
# Sabit yedek admin hesabı
# Şifre düz metin olarak saklanmaz; yalnızca tuz + PBKDF2 özeti gömülüdür.
# Varsayılan şifre (yalnızca geliştirici notu): KobiAdmin#1
# ---------------------------------------------------------------------------
ADMIN_USERNAME = "admin"
_ADMIN_SALT = bytes.fromhex("4b6f626943414d41646d696e53616c74")
_ADMIN_HASH = bytes.fromhex(
    "1a6e6503a02f5ecbaf0c1175169d451e03c2608d3bec6d8d281fafeba93ecf33"
)


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
    """Zaman damgasını UTC ISO-8601 olarak üretir."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """
    Şifreyi PBKDF2-HMAC-SHA256 ile özetler.

    Returns:
        (salt, hash) ikilisi. salt verilmezse kriptografik rastgele üretilir.
    """
    if salt is None:
        salt = secrets.token_bytes(SALT_LEN)
    ozet = hashlib.pbkdf2_hmac(
        PBKDF2_HASH_NAME,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return salt, ozet


def verify_password(password: str, salt: bytes, expected_hash: bytes) -> bool:
    """Zamanlama-güvenli (constant-time) şifre karşılaştırması yapar."""
    _, ozet = hash_password(password, salt=salt)
    return hmac.compare_digest(ozet, expected_hash)


class AuthError(Exception):
    """Kimlik doğrulama / kullanıcı işlemleri için uygulama hatası."""


class AuthManager:
    """
    SQLite tabanlı kullanıcı deposu ve sabit admin doğrulayıcısı.

    Admin kaydı veritabanında tutulmaz; böylece silinemez veya güncellenemez.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else get_app_data_dir() / "users.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        baglanti = sqlite3.connect(str(self.db_path))
        baglanti.row_factory = sqlite3.Row
        return baglanti

    def _init_db(self) -> None:
        """Kullanıcı tablosunu yoksa oluşturur."""
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
            baglanti.commit()

    def is_first_run(self) -> bool:
        """
        Sistemde henüz ana hesap yoksa True döner (Clean Installation).

        Sabit admin bu sayıya dahil edilmez; her zaman ayrıca geçerlidir.
        """
        return self.user_count() == 0

    def user_count(self) -> int:
        """Kayıtlı (admin hariç) kullanıcı sayısını döndürür."""
        with self._connect() as baglanti:
            satir = baglanti.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            return int(satir["n"]) if satir else 0

    def validate_username(self, username: str) -> str:
        """Kullanıcı adını temizler ve kurallara göre doğrular; geçerli adı döndürür."""
        ad = (username or "").strip()
        if len(ad) < MIN_USERNAME_LEN or len(ad) > MAX_USERNAME_LEN:
            raise AuthError(
                f"Kullanıcı adı {MIN_USERNAME_LEN}–{MAX_USERNAME_LEN} karakter olmalıdır."
            )
        if not ad.replace("_", "").isalnum():
            raise AuthError(
                "Kullanıcı adı yalnızca harf, rakam ve alt çizgi içerebilir."
            )
        if ad.lower() == ADMIN_USERNAME:
            raise AuthError(
                f"'{ADMIN_USERNAME}' adı sistem yedek hesabına aittir; kullanılamaz."
            )
        return ad

    def validate_password(self, password: str) -> None:
        """Şifre uzunluk kuralını kontrol eder."""
        if not password or len(password) < MIN_PASSWORD_LEN:
            raise AuthError(f"Şifre en az {MIN_PASSWORD_LEN} karakter olmalıdır.")

    def create_user(self, username: str, password: str) -> str:
        """
        Yeni ana hesap oluşturur. İlk kurulum sihirbazı bu metodu kullanır.

        Returns:
            Kaydedilen kullanıcı adı.
        """
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

    def authenticate(self, username: str, password: str) -> str:
        """
        Kullanıcı adı ve şifreyi doğrular.

        Başarılıysa normalize edilmiş kullanıcı adını döndürür;
        başarısızsa AuthError fırlatır.
        """
        ad = (username or "").strip()
        if not ad or password is None:
            raise AuthError("Kullanıcı adı ve şifre zorunludur.")

        # Sabit admin her zaman öncelikli ve değiştirilemez
        if ad.lower() == ADMIN_USERNAME:
            if self._verify_admin(password):
                return ADMIN_USERNAME
            raise AuthError("Kullanıcı adı veya şifre hatalı.")

        with self._connect() as baglanti:
            satir = baglanti.execute(
                "SELECT username, salt, password_hash FROM users WHERE username = ? COLLATE NOCASE",
                (ad,),
            ).fetchone()

        if satir is None:
            # Kullanıcı yoksa da aynı mesaj — kullanıcı enumerasyonunu zorlaştırır
            raise AuthError("Kullanıcı adı veya şifre hatalı.")

        if not verify_password(password, bytes(satir["salt"]), bytes(satir["password_hash"])):
            raise AuthError("Kullanıcı adı veya şifre hatalı.")

        return str(satir["username"])

    def _verify_admin(self, password: str) -> bool:
        """Gömülü admin hash'i ile zamanlama-güvenli karşılaştırma yapar."""
        ozet = hashlib.pbkdf2_hmac(
            PBKDF2_HASH_NAME,
            password.encode("utf-8"),
            _ADMIN_SALT,
            PBKDF2_ITERATIONS,
        )
        return hmac.compare_digest(ozet, _ADMIN_HASH)
