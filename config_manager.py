"""
JSON tabanlı kalıcı ayar okuma / yazma.

Varsayılan grid, kayıt klasörü, akış tercihleri ve kamera listesi
uygulama veri dizinindeki config.json dosyasında saklanır.
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from auth_manager import get_app_data_dir
from security.crypto_manager import bellege_coz, disk_icin_sifrele, gocet_duz_metin


# Uygulama varsayılanları — ilk açılışta bu şema yazılır
_VARSAYILANLAR: dict[str, Any] = {
    "grid_layout": 4,           # 1, 4, 9 veya 16
    "record_folder": "",        # boşsa kullanıcı Videos/KobiCAM kullanılır
    "snapshot_folder": "",      # boşsa kayıt klasörü kullanılır
    "window_geometry": "",      # pencere konumu/boyutu (base64)
    "splitter_sizes": [],       # sol panel / ızgara genişlikleri
    "display_quality": "low",  # low=sub-stream, high=main-stream
    "prefer_substream": True,  # eski anahtar; display_quality ile senkron
    "main_stream_on_zoom": True,
    "snapshot_format": "png",   # png veya jpg
    "record_format": "mp4",     # mp4 veya mkv
    "cameras": [],
    "devices": [],             # DVR/NVR / IP cihazları
    "grid_slots": [],          # hücrelere bağlı kamera id'leri
    "gdrive_enabled": False,
    "gdrive_folder_name": "KobiCAM_Cloud",
    "gdrive_retention_hours": 120,
    "gdrive_camera_ids": [],
    "gdrive_segment_seconds": 300,
    "gdrive_oauth_client_id": "",
    "gdrive_oauth_client_secret": "",
    "gdrive_delete_local": True,
    "analytics_enabled": False,
    "analytics_camera_id": "",
    "analytics_line": [],       # [x1, y1, x2, y2] 0–1
    "analytics_fps": 5,
    "web_enabled": False,
    "web_bind": "0.0.0.0",
    "web_port": 8765,
    "web_jwt_secret": "",
    "web_max_streams": 4,
    "ngrok_enabled": False,
    "ngrok_authtoken": "",
    "web_last_url": "",
}


class ConfigManager:
    """config.json dosyasını bellek ile senkron tutar."""

    def __init__(self, dosya: Path | None = None) -> None:
        self.path = Path(dosya) if dosya else get_app_data_dir() / "config.json"
        self._veri: dict[str, Any] = deepcopy(_VARSAYILANLAR)
        self.load()

    def load(self) -> None:
        """Diskteki ayarları yükler; dosya yoksa varsayılanları yazar."""
        if not self.path.exists():
            self.save()
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                okunan = json.load(f)
            if isinstance(okunan, dict):
                self._veri = {**deepcopy(_VARSAYILANLAR), **okunan}
            self._veri["web_jwt_secret"] = ""
            duz = gocet_duz_metin(deepcopy(self._veri))
            bellege_coz(self._veri)
            self._cihazlari_gocet()
            if duz:
                self.save()
        except (OSError, json.JSONDecodeError):
            self._veri = deepcopy(_VARSAYILANLAR)

    def save(self) -> None:
        """Sırları ENC: olarak diske yazar; bellek düz metin kalır."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        yazilacak = disk_icin_sifrele(self._veri)
        gecici = self.path.with_suffix(".tmp")
        with gecici.open("w", encoding="utf-8") as f:
            json.dump(yazilacak, f, ensure_ascii=False, indent=2)
        gecici.replace(self.path)
        jwt_yol = self.path.parent / "web_jwt_secret.txt"
        if jwt_yol.is_file():
            try:
                jwt_yol.unlink()
            except OSError:
                pass

    def get(self, anahtar: str, varsayilan: Any = None) -> Any:
        return self._veri.get(anahtar, varsayilan)

    def set(self, anahtar: str, deger: Any, kaydet: bool = True) -> None:
        self._veri[anahtar] = deger
        if kaydet:
            self.save()

    @property
    def data(self) -> dict[str, Any]:
        """Ayar sözlüğünün kopyasını döndürür."""
        return deepcopy(self._veri)

    def cameras(self) -> list[dict[str, Any]]:
        """Kayıtlı kamera listesinin kopyasını döndürür (yalnızca yayın kanalları)."""
        ham = self.get("cameras") or []
        return deepcopy(ham) if isinstance(ham, list) else []

    def devices(self) -> list[dict[str, Any]]:
        ham = self.get("devices") or []
        return deepcopy(ham) if isinstance(ham, list) else []

    def device_by_id(self, cihaz_id: str) -> dict[str, Any] | None:
        for cihaz in self.devices():
            if cihaz.get("id") == cihaz_id:
                return cihaz
        return None

    def device_by_ip(self, ip: str) -> dict[str, Any] | None:
        ip = (ip or "").strip()
        for cihaz in self.devices():
            if cihaz.get("ip") == ip:
                return cihaz
        return None

    def cameras_of_device(self, cihaz_id: str) -> list[dict[str, Any]]:
        return [k for k in self.cameras() if k.get("device_id") == cihaz_id]

    def _cihazlari_gocet(self) -> None:
        """Eski tek listeli kayıtları cihaz + kamera olarak ayırır."""
        cihazlar = self.devices()
        kameralar = self.cameras()
        if cihazlar:
            return
        yeni_cihazlar: list[dict[str, Any]] = []
        yeni_kameralar: list[dict[str, Any]] = []
        ip_map: dict[str, str] = {}
        degisti = False
        for k in kameralar:
            ip = str(k.get("ip") or "").strip()
            kanal_mi = bool(k.get("channel") or k.get("source_token"))
            url_var = bool((k.get("main_url") or "").strip())
            if ip and ip not in ip_map:
                cid = uuid.uuid4().hex
                ip_map[ip] = cid
                yeni_cihazlar.append(
                    {
                        "id": cid,
                        "name": str(k.get("name") or ip).split(" · ")[0],
                        "ip": ip,
                        "port": k.get("port") or 554,
                        "onvif_port": 80,
                        "media_port": 34567,
                        "username": k.get("username") or "",
                        "password": k.get("password") or "",
                        "xaddrs": k.get("xaddrs") or "",
                        "source": k.get("source") or "manual",
                        "vendor": "auto",
                    }
                )
                degisti = True
            if kanal_mi or url_var:
                if ip:
                    k = dict(k)
                    k["device_id"] = ip_map.get(ip, k.get("device_id") or "")
                yeni_kameralar.append(k)
            else:
                degisti = True
        if not degisti and not yeni_cihazlar:
            return
        self._veri["devices"] = yeni_cihazlar or cihazlar
        self._veri["cameras"] = yeni_kameralar
        self.save()

    def upsert_device(self, cihaz: dict[str, Any], from_scan: bool = False) -> dict[str, Any]:
        liste = self.devices()
        indeks = None
        for i, mevcut in enumerate(liste):
            if cihaz.get("id") and mevcut.get("id") == cihaz["id"]:
                indeks = i
                break
            if cihaz.get("ip") and mevcut.get("ip") == cihaz.get("ip"):
                indeks = i
                break
        if from_scan and indeks is not None:
            mevcut = liste[indeks]
            birlesik = dict(mevcut)
            if cihaz.get("xaddrs") and not mevcut.get("xaddrs"):
                birlesik["xaddrs"] = cihaz.get("xaddrs")
            if cihaz.get("name") and (
                not (mevcut.get("name") or "").strip()
                or mevcut.get("name") == mevcut.get("ip")
            ):
                birlesik["name"] = cihaz.get("name")
            if cihaz.get("source"):
                birlesik["source"] = cihaz.get("source")
            liste[indeks] = birlesik
            self.set("devices", liste)
            return deepcopy(birlesik)
        if indeks is None:
            yeni = dict(cihaz)
            yeni.setdefault("id", uuid.uuid4().hex)
            yeni.setdefault("onvif_port", 80)
            yeni.setdefault("media_port", 34567)
            yeni.setdefault("vendor", "auto")
            liste.append(yeni)
            self.set("devices", liste)
            return deepcopy(yeni)
        mevcut = liste[indeks]
        liste[indeks] = {**mevcut, **cihaz, "id": mevcut.get("id")}
        self.set("devices", liste)
        return deepcopy(liste[indeks])

    def remove_device(self, cihaz_id: str) -> list[str]:
        """Cihazı ve ona bağlı kameraları siler. Silinen kamera id'lerini döner."""
        kamera_ids = [k.get("id") for k in self.cameras() if k.get("device_id") == cihaz_id]
        self.set("devices", [d for d in self.devices() if d.get("id") != cihaz_id])
        self.set("cameras", [k for k in self.cameras() if k.get("device_id") != cihaz_id])
        return [str(x) for x in kamera_ids if x]

    def camera_by_id(self, kamera_id: str) -> dict[str, Any] | None:
        for kamera in self.cameras():
            if kamera.get("id") == kamera_id:
                return kamera
        return None

    def upsert_camera(self, cam: dict[str, Any], from_scan: bool = False) -> dict[str, Any]:
        """IP veya id ile kamerayı ekler / günceller. Tarama mevcut URL/şifreyi silmez."""
        kameralar = self.cameras()
        indeks = None
        for i, mevcut in enumerate(kameralar):
            if cam.get("id") and mevcut.get("id") == cam["id"]:
                indeks = i
                break
            if self._ayni_cihaz_kanali(mevcut, cam):
                indeks = i
                break

        if from_scan:
            ayni_ip = [k for k in kameralar if k.get("ip") == cam.get("ip")]
            if ayni_ip:
                if indeks is None:
                    return deepcopy(ayni_ip[0])
                mevcut = kameralar[indeks]
                birlesik = dict(mevcut)
                if cam.get("xaddrs") and not mevcut.get("xaddrs"):
                    birlesik["xaddrs"] = cam.get("xaddrs")
                if not (mevcut.get("name") or "").strip():
                    birlesik["name"] = cam.get("name") or mevcut.get("name")
                kameralar[indeks] = birlesik
                self.set("cameras", kameralar)
                return deepcopy(birlesik)

        if indeks is None:
            yeni = dict(cam)
            yeni.setdefault("id", uuid.uuid4().hex)
            kameralar.append(yeni)
            self.set("cameras", kameralar)
            return deepcopy(yeni)

        mevcut = kameralar[indeks]
        kameralar[indeks] = {**mevcut, **cam, "id": mevcut.get("id")}
        self.set("cameras", kameralar)
        return deepcopy(kameralar[indeks])

    @staticmethod
    def _ayni_cihaz_kanali(mevcut: dict[str, Any], cam: dict[str, Any]) -> bool:
        if not cam.get("ip") or mevcut.get("ip") != cam.get("ip"):
            return False
        cam_ch = cam.get("source_token") or cam.get("channel")
        mevcut_ch = mevcut.get("source_token") or mevcut.get("channel")
        if cam_ch:
            return mevcut_ch == cam_ch
        return not mevcut_ch

    def uygula_kanallar(
        self,
        ip: str,
        kanallar: list[dict[str, Any]],
        device_id: str = "",
    ) -> list[dict[str, Any]]:
        """Cihaza ait kameraları ONVIF/RTSP kanallarıyla değiştirir."""
        ip = (ip or "").strip()
        if not ip or not kanallar:
            return []
        kameralar = self.cameras()
        if device_id:
            eski = [k for k in kameralar if k.get("device_id") == device_id]
            diger = [k for k in kameralar if k.get("device_id") != device_id]
        else:
            eski = [k for k in kameralar if k.get("ip") == ip]
            diger = [k for k in kameralar if k.get("ip") != ip]
        token_map = {}
        for k in eski:
            anahtar = str(k.get("source_token") or k.get("channel") or "")
            if anahtar:
                token_map[anahtar] = k

        yazilan: list[dict[str, Any]] = []
        for ch in kanallar:
            kayit = dict(ch)
            kayit["ip"] = ip
            if device_id:
                kayit["device_id"] = device_id
            anahtar = str(kayit.get("source_token") or kayit.get("channel") or "")
            onceki = token_map.get(anahtar)
            if onceki is not None:
                kayit["id"] = onceki.get("id")
                eski_ad = str(onceki.get("name") or "").strip()
                if eski_ad and "Kanal" not in eski_ad and not eski_ad.startswith("ONVIF "):
                    kayit["name"] = eski_ad
            else:
                kayit.setdefault("id", uuid.uuid4().hex)
            yazilan.append(kayit)

        self.set("cameras", diger + yazilan)
        return [deepcopy(k) for k in yazilan]

    def remove_camera(self, kamera_id: str) -> None:
        kameralar = [k for k in self.cameras() if k.get("id") != kamera_id]
        self.set("cameras", kameralar)

    @staticmethod
    def varsayilan_klasor() -> Path:
        return Path.home() / "Videos" / "KobiCAM"

    def media_dir(self) -> Path:
        """Video kayıtlarının klasörü. Boş ayarda Videos/KobiCAM kullanılır."""
        ayar = str(self.get("record_folder") or "").strip()
        klasor = Path(ayar) if ayar else self.varsayilan_klasor()
        klasor.mkdir(parents=True, exist_ok=True)
        return klasor

    def snapshot_dir(self) -> Path:
        """Anlık görüntü klasörü. Boş ayarda kayıt klasörü kullanılır."""
        ayar = str(self.get("snapshot_folder") or "").strip()
        if not ayar:
            return self.media_dir()
        klasor = Path(ayar)
        klasor.mkdir(parents=True, exist_ok=True)
        return klasor

    def display_quality(self) -> str:
        """Açılış / genel görüntü kalitesi: 'low' veya 'high'."""
        q = str(self.get("display_quality") or "").lower()
        if q in ("low", "high"):
            return q
        return "low" if self.get("prefer_substream", True) else "high"

    def set_display_quality(self, kalite: str, kaydet: bool = True) -> None:
        kalite = "high" if str(kalite).lower() == "high" else "low"
        self.set("display_quality", kalite, kaydet=False)
        self.set("prefer_substream", kalite == "low", kaydet=kaydet)

    def grid_slots(self) -> list[str]:
        ham = self.get("grid_slots") or []
        if not isinstance(ham, list):
            return []
        return [str(x) if x else "" for x in ham]


def kamera_rtsp(kamera: dict[str, Any] | None, prefer_sub: bool = True) -> str:
    """Kameranın canlı RTSP adresini döndürür (sub tercih)."""
    if not kamera:
        return ""
    sub = str(kamera.get("sub_url") or "").strip()
    main = str(kamera.get("main_url") or "").strip()
    if prefer_sub and sub:
        return sub
    return main or sub
