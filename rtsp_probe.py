"""
RTSP DESCRIBE yoklaması ve üretici yol şablonlarıyla kanal bulma.

DVR/NVR cihazlarının çoğu ONVIF'i kapalı gönderir; bu modül ONVIF olmadan da
RTSP üzerinden kanalları bulur. Hikvision/Dahua/XM cihazları RTSP'de Digest
kimlik doğrulaması ister, bu yüzden Basic tek başına yetmez.
"""

from __future__ import annotations

import base64
import hashlib
import re
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

_ZAMAN_ASIMI = 3.0
_MAKS_KANAL = 32

# (anahtar, etiket, main yolu, sub yolu) — {n} kanal, {u}/{p} kimlik
SABLONLAR: list[tuple[str, str, str, str]] = [
    ("hikvision", "Hikvision / uyumlu", "/Streaming/Channels/{n}01", "/Streaming/Channels/{n}02"),
    ("dahua", "Dahua / uyumlu", "/cam/realmonitor?channel={n}&subtype=0", "/cam/realmonitor?channel={n}&subtype=1"),
    ("xm", "XM / Xiongmai", "/user={u}&password={p}&channel={n}&stream=0.sdp?", "/user={u}&password={p}&channel={n}&stream=1.sdp?"),
    ("hik_eski", "Hikvision (eski)", "/h264/ch{n}/main/av_stream", "/h264/ch{n}/sub/av_stream"),
    ("ch_numarali", "Genel ch/av_stream", "/ch{n}/main/av_stream", "/ch{n}/sub/av_stream"),
    ("live", "Genel live", "/live/ch{n}", "/live/ch{n}"),
    ("live_00", "Genel live_0", "/live/ch{n:02d}_0", "/live/ch{n:02d}_1"),
    ("chxx", "Genel ch/0", "/ch{n:02d}/0", "/ch{n:02d}/1"),
    ("profile", "TVT / Provision", "/profile{n}", "/profile{n}"),
    ("uniview", "Uniview", "/unicast/c{n}/s0/live", "/unicast/c{n}/s1/live"),
    ("media", "Genel media", "/media/video{n}", "/media/video{n}"),
]

_VENDOR_ESLESME = {
    "hikvision": ("hikvision", "hik_eski", "ch_numarali"),
    "dahua": ("dahua",),
    "xm": ("xm", "live_00", "chxx"),
    "uniview": ("uniview", "media"),
    "tvt": ("profile", "chxx"),
}

# Üreticiye özgü açık portlar → şablon ve ONVIF portu tahmini
URETICI_PORTLARI: tuple[tuple[int, str], ...] = (
    (34567, "xm"),
    (8899, "xm"),
    (37777, "dahua"),
    (8000, "hikvision"),
)

# Üreticiye göre denenecek ONVIF portları
URETICI_ONVIF_PORTLARI: dict[str, tuple[int, ...]] = {
    "xm": (8899, 80, 85, 34567),
    "dahua": (80, 8000),
    "hikvision": (80, 8000),
    "uniview": (80, 8000),
    "tvt": (80, 8000, 5000),
}


def _rasgele() -> str:
    return uuid.uuid4().hex[:16]


def _digest_basligi(meydan: str, kullanici: str, sifre: str, uri: str, metot: str = "DESCRIBE") -> str:
    alanlar = dict(re.findall(r'(\w+)="([^"]*)"', meydan))
    realm = alanlar.get("realm", "")
    nonce = alanlar.get("nonce", "")
    opaque = alanlar.get("opaque")
    qop = alanlar.get("qop", "")

    ha1 = hashlib.md5(f"{kullanici}:{realm}:{sifre}".encode("utf-8")).hexdigest()
    ha2 = hashlib.md5(f"{metot}:{uri}".encode("utf-8")).hexdigest()

    parcalar = [
        f'username="{kullanici}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
    ]
    if qop:
        cnonce = _rasgele()
        nc = "00000001"
        yanit = hashlib.md5(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}".encode("utf-8")).hexdigest()
        parcalar += [f'response="{yanit}"', "qop=auth", f"nc={nc}", f'cnonce="{cnonce}"']
    else:
        yanit = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode("utf-8")).hexdigest()
        parcalar.append(f'response="{yanit}"')
    if opaque is not None:
        parcalar.append(f'opaque="{opaque}"')
    return "Digest " + ", ".join(parcalar)


def _istek(uri: str, cseq: int, yetki: str = "") -> bytes:
    satirlar = [
        f"DESCRIBE {uri} RTSP/1.0",
        f"CSeq: {cseq}",
        "Accept: application/sdp",
        "User-Agent: KobiCAM",
    ]
    if yetki:
        satirlar.append(f"Authorization: {yetki}")
    return ("\r\n".join(satirlar) + "\r\n\r\n").encode("utf-8", errors="replace")


def _oku(soket: socket.socket, zaman_asimi: float) -> str:
    soket.settimeout(zaman_asimi)
    tampon = b""
    while b"\r\n\r\n" not in tampon and len(tampon) < 8192:
        try:
            parca = soket.recv(2048)
        except OSError:
            break
        if not parca:
            break
        tampon += parca
    return tampon.decode("utf-8", errors="replace")


def _durum_kodu(yanit: str) -> int:
    ilk = (yanit.splitlines() or [""])[0]
    es = re.search(r"RTSP/\d\.\d\s+(\d{3})", ilk)
    return int(es.group(1)) if es else 0


def rtsp_dene(
    host: str,
    port: int,
    yol: str,
    kullanici: str = "",
    sifre: str = "",
    zaman_asimi: float = _ZAMAN_ASIMI,
) -> str:
    """
    Tek bir RTSP yolunu dener.

    Returns:
        'ok' | 'auth' | 'yok' | 'kapali'
    """
    uri = f"rtsp://{host}:{int(port)}{yol}"
    try:
        soket = socket.create_connection((host, int(port)), timeout=zaman_asimi)
    except OSError:
        return "kapali"
    try:
        soket.sendall(_istek(uri, 1))
        yanit = _oku(soket, zaman_asimi)
        kod = _durum_kodu(yanit)
        if kod == 200:
            return "ok"
        if kod == 401 and kullanici:
            meydan = ""
            for satir in yanit.splitlines():
                if satir.lower().startswith("www-authenticate:"):
                    meydan = satir.split(":", 1)[1].strip()
                    if meydan.lower().startswith("digest"):
                        break
            if meydan.lower().startswith("digest"):
                yetki = _digest_basligi(meydan, kullanici, sifre, uri)
            else:
                jeton = base64.b64encode(f"{kullanici}:{sifre}".encode("utf-8")).decode("ascii")
                yetki = f"Basic {jeton}"
            soket.sendall(_istek(uri, 2, yetki))
            yanit2 = _oku(soket, zaman_asimi)
            kod2 = _durum_kodu(yanit2)
            if kod2 == 200:
                return "ok"
            if kod2 == 401:
                return "auth"
            return "yok"
        if kod == 401:
            return "auth"
        if kod == 0:
            return "kapali"
        return "yok"
    except OSError:
        return "kapali"
    finally:
        try:
            soket.close()
        except OSError:
            pass


def _yol(sablon: str, kanal: int, kullanici: str, sifre: str) -> str:
    return sablon.format(
        n=kanal,
        u=quote(kullanici, safe=""),
        p=quote(sifre, safe=""),
    )


def rtsp_url(host: str, port: int, yol: str, kullanici: str, sifre: str) -> str:
    if "user=" in yol and "password=" in yol:
        return f"rtsp://{host}:{int(port)}{yol}"
    kimlik = ""
    if kullanici:
        kimlik = f"{quote(kullanici, safe='')}:{quote(sifre, safe='')}@"
    return f"rtsp://{kimlik}{host}:{int(port)}{yol}"


def _sablon_sirasi(vendor: str) -> list[tuple[str, str, str, str]]:
    vendor = (vendor or "auto").lower()
    tercih = _VENDOR_ESLESME.get(vendor)
    if not tercih:
        return list(SABLONLAR)
    once = [s for s in SABLONLAR if s[0] in tercih]
    sonra = [s for s in SABLONLAR if s[0] not in tercih]
    return once + sonra


def sablon_bul(
    host: str,
    port: int,
    kullanici: str,
    sifre: str,
    vendor: str = "auto",
) -> tuple[tuple[str, str, str, str] | None, str]:
    """
    1. kanalı deneyerek cihazın RTSP yol ailesini bulur.

    Returns:
        (şablon | None, durum)  durum: 'ok' | 'auth' | 'yol_yok' | 'kapali'
    """
    if not port_acik(host, port, 1.0):
        return None, "kapali"
    adaylar = _sablon_sirasi(vendor)
    sonuclar: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as havuz:
        isler = {
            havuz.submit(
                rtsp_dene, host, port, _yol(s[2], 1, kullanici, sifre), kullanici, sifre
            ): s[0]
            for s in adaylar
        }
        for gelecek, anahtar in isler.items():
            try:
                sonuclar[anahtar] = gelecek.result()
            except Exception:
                sonuclar[anahtar] = "kapali"

    for sablon in adaylar:
        if sonuclar.get(sablon[0]) == "ok":
            return sablon, "ok"
    durumlar = set(sonuclar.values())
    if "auth" in durumlar:
        return None, "auth"
    if "yok" in durumlar:
        return None, "yol_yok"
    return None, "kapali"


def kanallari_bul(
    host: str,
    port: int,
    kullanici: str,
    sifre: str,
    vendor: str = "auto",
    cihaz_adi: str = "",
    maks_kanal: int = _MAKS_KANAL,
) -> tuple[list[dict], str]:
    """
    RTSP şablonlarıyla kanal listesi çıkarır.

    Returns:
        (kanallar, durum)  durum: 'ok' | 'auth' | 'yol_yok' | 'kapali'
    """
    sablon, durum = sablon_bul(host, port, kullanici, sifre, vendor)
    if sablon is None:
        return [], durum

    anahtar, _etiket, main_yol, sub_yol = sablon
    taban = (cihaz_adi or host).strip()
    kanallar: list[dict] = []
    kacirdi = 0
    for no in range(1, int(maks_kanal) + 1):
        if no == 1:
            sonuc = "ok"
        else:
            sonuc = rtsp_dene(
                host, port, _yol(main_yol, no, kullanici, sifre), kullanici, sifre
            )
        if sonuc != "ok":
            kacirdi += 1
            if kacirdi >= 2:
                break
            continue
        kacirdi = 0
        kanallar.append(
            {
                "channel": no,
                "source_token": f"{anahtar}-{no}",
                "name": f"{taban} · Kanal {no}",
                "main_url": rtsp_url(host, port, _yol(main_yol, no, kullanici, sifre), kullanici, sifre),
                "sub_url": rtsp_url(host, port, _yol(sub_yol, no, kullanici, sifre), kullanici, sifre),
                "profile_token": "",
                "rtsp_template": anahtar,
            }
        )
    return kanallar, "ok" if kanallar else durum


def kanallari_uret(
    host: str,
    port: int,
    kullanici: str,
    sifre: str,
    sablon_anahtari: str,
    kanal_sayisi: int,
    cihaz_adi: str = "",
) -> list[dict]:
    """Doğrulama yapmadan, seçilen şablonla kanal kayıtları üretir."""
    sablon = next((s for s in SABLONLAR if s[0] == sablon_anahtari), None)
    if sablon is None:
        return []
    anahtar, _etiket, main_yol, sub_yol = sablon
    taban = (cihaz_adi or host).strip()
    return [
        {
            "channel": no,
            "source_token": f"{anahtar}-{no}",
            "name": f"{taban} · Kanal {no}",
            "main_url": rtsp_url(host, port, _yol(main_yol, no, kullanici, sifre), kullanici, sifre),
            "sub_url": rtsp_url(host, port, _yol(sub_yol, no, kullanici, sifre), kullanici, sifre),
            "profile_token": "",
            "rtsp_template": anahtar,
        }
        for no in range(1, max(1, int(kanal_sayisi)) + 1)
    ]


def port_acik(host: str, port: int, zaman_asimi: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=zaman_asimi):
            return True
    except OSError:
        return False


def uretici_tahmin(host: str, media_port: int = 0) -> tuple[str, list[int]]:
    """
    Açık portlara bakarak üreticiyi tahmin eder.

    XM/Xiongmai cihazlar 34567 (media port), Dahua 37777, Hikvision 8000 kullanır.

    Returns:
        (üretici | "", açık portlar)
    """
    adaylar: list[tuple[int, str]] = []
    if media_port:
        eslesme = dict(URETICI_PORTLARI).get(int(media_port), "")
        adaylar.append((int(media_port), eslesme))
    for port, uretici in URETICI_PORTLARI:
        if all(port != p for p, _u in adaylar):
            adaylar.append((port, uretici))

    acik: list[int] = []
    sonuc: dict[int, bool] = {}
    with ThreadPoolExecutor(max_workers=6) as havuz:
        isler = {havuz.submit(port_acik, host, p, 0.7): p for p, _u in adaylar}
        for gelecek, port in isler.items():
            try:
                sonuc[port] = bool(gelecek.result())
            except Exception:
                sonuc[port] = False
    bulunan = ""
    for port, uretici in adaylar:
        if sonuc.get(port):
            acik.append(port)
            if uretici and not bulunan:
                bulunan = uretici
    return bulunan, acik
