"""
Google Drive API v3 senkronu: OAuth, SQLite kuyruk, retry, saklama süresi.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from app_log import get_logger
from auth_manager import get_app_data_dir
from db_util import baglan, sema_bir_kez

_SCOPES = ("https://www.googleapis.com/auth/drive.file",)
_KOTA = "storageQuotaExceeded"
_log = get_logger("gdrive")

_KUYRUK_DDL = """
CREATE TABLE IF NOT EXISTS queue (
    path TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry REAL NOT NULL DEFAULT 0
);
"""


def token_yolu() -> Path:
    return get_app_data_dir() / "gdrive_token.json"


def kuyruk_yolu() -> Path:
    """Eski JSON kuyruk (göç için)."""
    return get_app_data_dir() / "gdrive_queue.json"


def kuyruk_db() -> Path:
    return get_app_data_dir() / "gdrive_queue.db"


def _kuyruk_hazir() -> None:
    sema_bir_kez(kuyruk_db(), _KUYRUK_DDL)
    eski = kuyruk_yolu()
    if not eski.is_file():
        return
    try:
        ham = json.loads(eski.read_text(encoding="utf-8"))
        ogeler = ham.get("items") if isinstance(ham, dict) else ham
        if not isinstance(ogeler, list):
            eski.unlink(missing_ok=True)
            return
        with baglan(kuyruk_db()) as bag:
            for oge in ogeler:
                if not isinstance(oge, dict) or not oge.get("path"):
                    continue
                bag.execute(
                    "INSERT OR IGNORE INTO queue (path, camera_id, status, attempts, next_retry) "
                    "VALUES (?,?,?,?,?)",
                    (
                        str(oge.get("path")),
                        str(oge.get("camera_id") or "kamera"),
                        str(oge.get("status") or "pending"),
                        int(oge.get("attempts") or 0),
                        float(oge.get("next_retry") or 0),
                    ),
                )
            bag.commit()
        eski.unlink(missing_ok=True)
    except Exception:
        _log.exception("JSON kuyruk göçü")


def kuyruga_ekle(kamera_id: str, dosya: str) -> None:
    _kuyruk_hazir()
    with baglan(kuyruk_db()) as bag:
        bag.execute(
            "INSERT OR IGNORE INTO queue (path, camera_id, status, attempts, next_retry) "
            "VALUES (?,?,?,?,?)",
            (dosya, kamera_id, "pending", 0, 0),
        )
        bag.commit()


def kuyruk_sayisi() -> int:
    _kuyruk_hazir()
    with baglan(kuyruk_db()) as bag:
        satir = bag.execute(
            "SELECT COUNT(*) AS n FROM queue WHERE status != 'done'"
        ).fetchone()
        return int(satir["n"]) if satir else 0


def _kuyruk_oku() -> list[dict[str, Any]]:
    _kuyruk_hazir()
    with baglan(kuyruk_db()) as bag:
        satirlar = bag.execute(
            "SELECT path, camera_id, status, attempts, next_retry FROM queue "
            "WHERE status != 'done'"
        ).fetchall()
    return [
        {
            "path": str(s["path"]),
            "camera_id": str(s["camera_id"]),
            "status": str(s["status"]),
            "attempts": int(s["attempts"]),
            "next_retry": float(s["next_retry"]),
        }
        for s in satirlar
    ]


def _kuyruk_kaydet(oge: dict[str, Any]) -> None:
    with baglan(kuyruk_db()) as bag:
        if oge.get("status") == "done":
            bag.execute("DELETE FROM queue WHERE path=?", (oge["path"],))
        else:
            bag.execute(
                "UPDATE queue SET camera_id=?, status=?, attempts=?, next_retry=? WHERE path=?",
                (
                    oge.get("camera_id") or "",
                    oge.get("status") or "pending",
                    int(oge.get("attempts") or 0),
                    float(oge.get("next_retry") or 0),
                    oge["path"],
                ),
            )
        bag.commit()


def oauth_calistir(client_id: str, client_secret: str) -> None:
    """Tarayıcıda Google OAuth; token diske yazılır (arka plan thread)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    cfg = {
        "installed": {
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(cfg, scopes=list(_SCOPES))
    creds = flow.run_local_server(port=0, prompt="consent")
    token_yolu().write_text(creds.to_json(), encoding="utf-8")


def backoff_saniye(attempts: int, taban: int = 15, tavan: int = 3600) -> int:
    return min(tavan, taban * (2 ** min(8, max(0, int(attempts)))))


def silinecek_drive_dosyalari(
    dosyalar: list[dict[str, Any]],
    esik_ts: float,
) -> list[str]:
    """createdTime eşiğin altındakilerin Drive id listesi (birim test)."""
    ids: list[str] = []
    for dosya in dosyalar:
        olus = str(dosya.get("createdTime") or "")
        try:
            ts = datetime.fromisoformat(olus.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if ts < esik_ts:
            fid = str(dosya.get("id") or "")
            if fid:
                ids.append(fid)
    return ids


def _kimlik_yukle():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    yol = token_yolu()
    if not yol.is_file():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(yol), scopes=list(_SCOPES))
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            yol.write_text(creds.to_json(), encoding="utf-8")
        return creds if creds and creds.valid else None
    except Exception:
        _log.exception("Drive token yenilenemedi")
        return None


def _servis(creds):
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _klasor_id(servis, ad: str, ebeveyn: str | None = None) -> str:
    from googleapiclient.errors import HttpError

    sorgu = f"name='{ad.replace(chr(39), '')}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if ebeveyn:
        sorgu += f" and '{ebeveyn}' in parents"
    try:
        cevap = servis.files().list(q=sorgu, spaces="drive", fields="files(id,name)").execute()
        dosyalar = cevap.get("files") or []
        if dosyalar:
            return str(dosyalar[0]["id"])
        govde: dict[str, Any] = {
            "name": ad,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if ebeveyn:
            govde["parents"] = [ebeveyn]
        olusan = servis.files().create(body=govde, fields="id").execute()
        return str(olusan["id"])
    except HttpError:
        _log.exception("Drive klasör")
        raise


class GDriveSyncThread(QThread):
    """Kuyruktaki MP4'leri yükler; eski Drive dosyalarını siler."""

    durum = pyqtSignal(str)
    hata = pyqtSignal(str)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._dur = False
        self._kok_id = ""
        self._alt: dict[str, str] = {}

    def request_stop(self) -> None:
        self._dur = True

    def run(self) -> None:
        self._dur = False
        _kuyruk_hazir()
        while not self._dur:
            if not self._config.get("gdrive_enabled"):
                self.msleep(3000)
                continue
            try:
                self._tur()
            except Exception as hata:
                _log.exception("Drive tur")
                self.hata.emit(str(hata))
            for _ in range(20):
                if self._dur:
                    return
                self.msleep(500)

    def _tur(self) -> None:
        creds = _kimlik_yukle()
        if creds is None:
            self.hata.emit("Google Drive oturumu yok. Ayarlar’dan bağlanın.")
            self.msleep(15000)
            return
        try:
            servis = _servis(creds)
            kok_ad = str(self._config.get("gdrive_folder_name") or "KobiCAM_Cloud")
            if not self._kok_id:
                self._kok_id = _klasor_id(servis, kok_ad)
            self._yukle(servis)
            self._temizlik(servis)
        except Exception:
            _log.exception("Drive API")
            raise

    def _yukle(self, servis) -> None:
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError

        ogeler = _kuyruk_oku()
        simdi = time.time()
        eszamanli = 0
        for oge in ogeler:
            if self._dur or eszamanli >= 2:
                break
            if float(oge.get("next_retry") or 0) > simdi:
                continue
            yol = Path(str(oge.get("path") or ""))
            if not yol.is_file():
                oge["status"] = "done"
                _kuyruk_kaydet(oge)
                continue
            kamera = str(oge.get("camera_id") or "kamera")
            oge["status"] = "uploading"
            _kuyruk_kaydet(oge)
            eszamanli += 1
            try:
                alt = self._alt.get(kamera)
                if not alt:
                    alt = _klasor_id(servis, kamera[:80], self._kok_id)
                    self._alt[kamera] = alt
                medya = MediaFileUpload(str(yol), mimetype="video/mp4", resumable=True)
                servis.files().create(
                    body={"name": yol.name, "parents": [alt]},
                    media_body=medya,
                    fields="id",
                ).execute()
                oge["status"] = "done"
                _kuyruk_kaydet(oge)
                self.durum.emit(f"Drive: {yol.name} yüklendi")
                if bool(self._config.get("gdrive_delete_local", True)):
                    try:
                        yol.unlink()
                    except OSError:
                        pass
            except HttpError as hata:
                metin = str(hata)
                oge["attempts"] = int(oge.get("attempts") or 0) + 1
                oge["status"] = "failed"
                kod = int(getattr(hata, "status_code", 0) or 0)
                if _KOTA in metin or "storageQuotaExceeded" in metin:
                    self.hata.emit("Google Drive kotası doldu; yükleme duraklatıldı.")
                    oge["next_retry"] = simdi + 3600
                    eszamanli = 99
                    _log.warning("Drive kota")
                elif kod in (429, 500, 502, 503) or "429" in metin or "50" in metin[:80]:
                    oge["next_retry"] = simdi + backoff_saniye(oge["attempts"])
                    self.hata.emit(f"Drive geçici hata, yeniden denenecek: {hata}")
                    _log.warning("Drive %s backoff", kod or "http")
                else:
                    oge["next_retry"] = simdi + backoff_saniye(oge["attempts"])
                    self.hata.emit(f"Drive yükleme hatası: {hata}")
                    _log.exception("Drive yükleme")
                _kuyruk_kaydet(oge)
            except OSError as hata:
                oge["attempts"] = int(oge.get("attempts") or 0) + 1
                oge["next_retry"] = simdi + backoff_saniye(oge["attempts"], taban=30)
                oge["status"] = "failed"
                _kuyruk_kaydet(oge)
                self.hata.emit(str(hata))
                _log.exception("Drive dosya")

    def _temizlik(self, servis) -> None:
        from googleapiclient.errors import HttpError

        saat = int(self._config.get("gdrive_retention_hours") or 120)
        if saat <= 0 or not self._kok_id:
            return
        esik = datetime.now(timezone.utc).timestamp() - saat * 3600
        try:
            altlar = (
                servis.files()
                .list(
                    q=f"'{self._kok_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                    fields="files(id)",
                    pageSize=100,
                )
                .execute()
                .get("files")
                or []
            )
        except HttpError:
            _log.exception("Drive temizlik liste")
            return
        klasorler = [self._kok_id] + [str(x["id"]) for x in altlar]
        for kid in klasorler:
            if self._dur:
                return
            sayfa = None
            while not self._dur:
                try:
                    cevap = (
                        servis.files()
                        .list(
                            q=f"'{kid}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false",
                            fields="nextPageToken, files(id,createdTime)",
                            pageToken=sayfa,
                            pageSize=100,
                        )
                        .execute()
                    )
                except HttpError:
                    _log.exception("Drive temizlik sayfa")
                    break
                silinecek = silinecek_drive_dosyalari(cevap.get("files") or [], esik)
                for fid in silinecek:
                    try:
                        servis.files().delete(fileId=fid).execute()
                    except Exception:
                        _log.exception("Drive silinemedi %s", fid)
                sayfa = cevap.get("nextPageToken")
                if not sayfa:
                    break
