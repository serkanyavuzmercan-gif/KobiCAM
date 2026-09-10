"""
ONVIF medya profilleri → DVR/NVR kanal listesi ve RTSP URI.

Kimlik girildikten sonra GetProfiles + GetStreamUri ile her video kaynağı
ayrı kamera kaydı olur (main + sub aynı kanalda birleşir).
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse, urlunparse

from network_scanner import mac_coz_ip, mac_normalize, yerel_ipv4_adresleri
from ptz_controller import _cihaz_url, _media_url_sec, _posta, _posta_ex, _xaddrs
from rtsp_probe import (
    URETICI_ONVIF_PORTLARI,
    kanallari_bul,
    port_acik,
    sablon_bul,
    uretici_tahmin,
)

_NS_TRT = "http://www.onvif.org/ver10/media/wsdl"
_NS_TR2 = "http://www.onvif.org/ver20/media/wsdl"
_NS_TT = "http://www.onvif.org/ver10/schema"
_NS_TDS = "http://www.onvif.org/ver10/device/wsdl"

_HATA_METIN = {
    "auth": "Kullanıcı adı veya şifre cihaz tarafından reddedildi.",
    "timeout": "Cihaz yanıt vermedi (zaman aşımı). IP ve ONVIF portunu kontrol edin.",
    "refused": "Cihaza bağlanılamadı. IP veya ONVIF portu yanlış olabilir.",
    "baglanti": "Cihaza ağ üzerinden ulaşılamadı.",
    "fault": "Cihaz ONVIF isteğini kabul etmedi.",
    "yanıt yok": "Cihaz ONVIF yanıtı vermedi.",
}


def _yerel(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _kimlik_ekle(url: str, kullanici: str, sifre: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    url = url.replace("&amp;", "&")
    if not kullanici.strip():
        return url
    ayr = urlparse(url)
    if ayr.username:
        return url
    host = ayr.hostname or ""
    if not host:
        return url
    netloc = f"{quote(kullanici.strip(), safe='')}:{quote(sifre, safe='')}@{host}"
    if ayr.port:
        netloc += f":{ayr.port}"
    return urlunparse((ayr.scheme or "rtsp", netloc, ayr.path, ayr.params, ayr.query, ayr.fragment))


def _cocuk(el: ET.Element, ad: str) -> ET.Element | None:
    for c in el:
        if _yerel(c.tag) == ad:
            return c
    return None


def _metin(el: ET.Element | None) -> str:
    if el is None or not el.text:
        return ""
    return el.text.strip()


def _iter_ad(kok: ET.Element, ad: str):
    for el in kok.iter():
        if _yerel(el.tag) == ad:
            yield el


def _xml_kok(xml: str) -> ET.Element | None:
    xml = (xml or "").strip()
    if not xml:
        return None
    try:
        return ET.fromstring(xml)
    except ET.ParseError:
        return None


def onvif_mac_al(device_url: str, kullanici: str, sifre: str) -> str:
    """GetNetworkInterfaces SOAP yanıtından donanım MAC'ini okur."""
    url = (device_url or "").strip()
    if not url:
        return ""
    xml, _hata = _posta_ex(
        url,
        f'<tds:GetNetworkInterfaces xmlns:tds="{_NS_TDS}"/>',
        kullanici,
        sifre,
        soap_action=f"{_NS_TDS}/GetNetworkInterfaces",
        zaman_asimi=4,
    )
    kok = _xml_kok(xml)
    if kok is None:
        return ""
    for el in kok.iter():
        ad = _yerel(el.tag).lower()
        if ad in ("hwaddress", "mac", "physaddress") and (el.text or "").strip():
            mac = mac_normalize(el.text.strip())
            if mac:
                return mac
    return ""


def _mac_topla(ip: str, cihaz_url: str, kullanici: str, sifre: str) -> str:
    mac = onvif_mac_al(cihaz_url, kullanici, sifre) if cihaz_url else ""
    return mac or mac_coz_ip(ip)


def _profilleri_ayikla(xml: str) -> list[dict]:
    kok = _xml_kok(xml)
    if kok is None:
        return []
    liste: list[dict] = []
    gorulen: set[str] = set()
    adaylar = list(_iter_ad(kok, "Profiles")) + list(_iter_ad(kok, "Profile"))
    for el in adaylar:
        token = el.attrib.get("token") or ""
        if not token or token in gorulen:
            continue
        gorulen.add(token)
        ad = _metin(_cocuk(el, "Name"))
        kaynak = ""
        vsc = None
        for c in _iter_ad(el, "VideoSourceConfiguration"):
            vsc = c
            break
        if vsc is not None:
            kaynak = _metin(_cocuk(vsc, "SourceToken")) or vsc.attrib.get("token") or ""
        genislik = 0
        for w in _iter_ad(el, "Width"):
            try:
                genislik = int(_metin(w) or "0")
            except ValueError:
                genislik = 0
            break
        encoder = False
        for _ in _iter_ad(el, "VideoEncoderConfiguration"):
            encoder = True
            break
        if not encoder and not kaynak:
            continue
        liste.append(
            {
                "token": token,
                "name": ad,
                "source_token": kaynak or token,
                "width": genislik,
            }
        )
    return liste


def _kaynaklari_ayikla(xml: str) -> list[str]:
    kok = _xml_kok(xml)
    if kok is None:
        return []
    tokenler: list[str] = []
    gorulen: set[str] = set()
    for el in list(_iter_ad(kok, "VideoSources")) + list(_iter_ad(kok, "VideoSource")):
        token = el.attrib.get("token") or _metin(_cocuk(el, "token"))
        if not token or token in gorulen:
            continue
        gorulen.add(token)
        tokenler.append(token)
    return tokenler


def _uri_ayikla(xml: str) -> str:
    kok = _xml_kok(xml)
    if kok is not None:
        for el in _iter_ad(kok, "Uri"):
            metin = _metin(el)
            if metin.lower().startswith("rtsp"):
                return metin
    es = re.search(r"(rtsp://[^<\s\"]+)", xml or "", re.I)
    return es.group(1).rstrip("\\") if es else ""


def _servis_adres(xml: str, anahtar: str) -> str:
    kok = _xml_kok(xml)
    if kok is None:
        return ""
    for srv in _iter_ad(kok, "Service"):
        ns = _metin(_cocuk(srv, "Namespace")).lower()
        if anahtar not in ns:
            continue
        addr = _metin(_cocuk(srv, "XAddr"))
        if addr:
            return addr.strip()
    return ""


def _stream_uri(
    media: str,
    token: str,
    kullanici: str,
    sifre: str,
    media2: bool = False,
) -> str:
    if media2:
        govde = f"""
        <tr2:GetStreamUri xmlns:tr2="{_NS_TR2}">
          <tr2:Protocol>RtspUnicast</tr2:Protocol>
          <tr2:ProfileToken>{token}</tr2:ProfileToken>
        </tr2:GetStreamUri>
        """
        action = f"{_NS_TR2}/GetStreamUri"
    else:
        govde = f"""
        <trt:GetStreamUri xmlns:trt="{_NS_TRT}" xmlns:tt="{_NS_TT}">
          <trt:StreamSetup>
            <tt:Stream>RTP-Unicast</tt:Stream>
            <tt:Transport>
              <tt:Protocol>RTSP</tt:Protocol>
            </tt:Transport>
          </trt:StreamSetup>
          <trt:ProfileToken>{token}</trt:ProfileToken>
        </trt:GetStreamUri>
        """
        action = f"{_NS_TRT}/GetStreamUri"
    yanit = _posta(
        media,
        govde,
        kullanici,
        sifre,
        soap_action=action,
        zaman_asimi=6,
    )
    return _uri_ayikla(yanit)


def _cihaz_adaylari(ip: str, xaddrs: str, onvif_port: int, vendor: str = "") -> list[str]:
    adaylar: list[str] = []
    gorulen: set[str] = set()

    def ekle(url: str) -> None:
        url = (url or "").strip()
        if url and url not in gorulen:
            gorulen.add(url)
            adaylar.append(url)

    for jeton in (xaddrs or "").split():
        if jeton.strip().startswith("http"):
            ekle(jeton.strip())
    ekle(_cihaz_url(ip, xaddrs))
    oncelik = URETICI_ONVIF_PORTLARI.get((vendor or "").lower(), ())
    portlar: list[int] = []
    for p in (onvif_port, *oncelik, 80, 8899, 8000, 8080, 85, 2020, 10080):
        try:
            p = int(p)
        except (TypeError, ValueError):
            continue
        if p not in portlar:
            portlar.append(p)
    for p in portlar:
        host = ip if p in (80, 443) else f"{ip}:{p}"
        ekle(f"http://{host}/onvif/device_service")
        ekle(f"http://{host}/onvif/device")
        if p == 443:
            ekle(f"https://{ip}/onvif/device_service")
    return adaylar


def _hata_yaz(kod: str) -> str:
    return _HATA_METIN.get(kod, kod or "Cihaza bağlanılamadı.")


def _tcp_acik(host: str, port: int, timeout: float = 0.45) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _url_host_port(url: str) -> tuple[str, int]:
    ayr = urlparse(url)
    host = ayr.hostname or ""
    port = ayr.port or (443 if (ayr.scheme or "").lower() == "https" else 80)
    return host, int(port)


def _acik_adresler(ip: str, xaddrs: str, onvif_port: int, vendor: str = "") -> list[str]:
    """Aday ONVIF URL'lerinden yalnızca portu açık olanları döndürür."""
    adaylar = _cihaz_adaylari(ip, xaddrs, onvif_port, vendor)
    gruplar: dict[tuple[str, int], list[str]] = {}
    for url in adaylar:
        host, port = _url_host_port(url)
        if host:
            gruplar.setdefault((host, port), []).append(url)
    if not gruplar:
        return []
    acik: set[tuple[str, int]] = set()
    with ThreadPoolExecutor(max_workers=8) as havuz:
        isler = {havuz.submit(_tcp_acik, h, p, 0.7): (h, p) for h, p in gruplar}
        for gelecek, hedef in isler.items():
            try:
                if gelecek.result():
                    acik.add(hedef)
            except Exception:
                pass
    return [url for hedef, urls in gruplar.items() if hedef in acik for url in urls]


def _endpoint_bul(
    ip: str,
    kullanici: str,
    sifre: str,
    xaddrs: str,
    onvif_port: int,
    vendor: str = "",
) -> tuple[str, str, str]:
    """Çalışan ONVIF device URL'sini dener. Dönüş: (url, cap_xml, hata)."""
    son_hata = "yanıt yok"
    tarih_govde = f'<tds:GetSystemDateAndTime xmlns:tds="{_NS_TDS}"/>'
    cap_govde = (
        f'<tds:GetCapabilities xmlns:tds="{_NS_TDS}">'
        "<tds:Category>All</tds:Category></tds:GetCapabilities>"
    )
    acik = _acik_adresler(ip, xaddrs, onvif_port, vendor)
    if not acik:
        return "", "", "refused"
    for url in acik:
        # Kimliksiz, ucuz yoklama: ONVIF servisi burada mı?
        canli, hata = _posta_ex(
            url,
            tarih_govde,
            "",
            "",
            soap_action=f"{_NS_TDS}/GetSystemDateAndTime",
            zaman_asimi=3,
        )
        if hata in ("timeout", "baglanti", "refused") or hata.startswith("http_"):
            # Port açık ama ONVIF konuşmuyor; bu adresi zorlamanın anlamı yok.
            son_hata = hata if hata != "yanıt yok" else son_hata
            continue
        if not canli or ("DateTime" not in canli and "UTCDateTime" not in canli and "Envelope" not in canli):
            cap, hata = _posta_ex(
                url,
                cap_govde,
                kullanici,
                sifre,
                soap_action=f"{_NS_TDS}/GetCapabilities",
                zaman_asimi=5,
            )
            if hata == "auth":
                return url, cap, "auth"
            if not cap:
                son_hata = hata or son_hata
                continue
            if "XAddr" in cap or "Capabilities" in cap:
                return url, cap, ""
            son_hata = hata or son_hata
            continue
        cap, hata = _posta_ex(
            url,
            cap_govde,
            kullanici,
            sifre,
            soap_action=f"{_NS_TDS}/GetCapabilities",
            zaman_asimi=8,
        )
        if hata == "auth":
            return url, cap, "auth"
        if cap and ("XAddr" in cap or "Capabilities" in cap):
            return url, cap, ""
        servis, hata2 = _posta_ex(
            url,
            f'<tds:GetServices xmlns:tds="{_NS_TDS}"><tds:IncludeCapability>true</tds:IncludeCapability></tds:GetServices>',
            kullanici,
            sifre,
            soap_action=f"{_NS_TDS}/GetServices",
            zaman_asimi=6,
        )
        if hata2 == "auth":
            return url, servis, "auth"
        if servis and "XAddr" in servis:
            return url, servis, ""
        son_hata = hata or hata2 or son_hata
    return "", "", son_hata


def _profilleri_cek(media: str, kullanici: str, sifre: str) -> tuple[list[dict], bool]:
    xml = _posta(
        media,
        f'<trt:GetProfiles xmlns:trt="{_NS_TRT}"/>',
        kullanici,
        sifre,
        soap_action=f"{_NS_TRT}/GetProfiles",
        zaman_asimi=8,
    )
    profiller = _profilleri_ayikla(xml)
    if profiller:
        return profiller, False
    xml2 = _posta(
        media,
        f'<tr2:GetProfiles xmlns:tr2="{_NS_TR2}"/>',
        kullanici,
        sifre,
        soap_action=f"{_NS_TR2}/GetProfiles",
        zaman_asimi=8,
    )
    return _profilleri_ayikla(xml2), True


def _kanallara_grupla(
    profiller: list[dict],
    uri_map: dict[str, str],
    kullanici: str,
    sifre: str,
    cihaz_adi: str,
    ip: str,
) -> list[dict]:
    gruplar: dict[str, list[dict]] = {}
    for p in profiller:
        p["url"] = _kimlik_ekle(uri_map.get(p["token"], ""), kullanici, sifre)
        if not p["url"]:
            continue
        gruplar.setdefault(p["source_token"], []).append(p)
    if not gruplar:
        return []
    taban = (cihaz_adi or ip or "DVR").strip()
    kanallar: list[dict] = []
    for no, kaynak in enumerate(gruplar.keys(), start=1):
        adaylar = sorted(
            gruplar[kaynak],
            key=lambda x: int(x.get("width") or 0),
            reverse=True,
        )
        main = adaylar[0]
        sub = adaylar[-1] if len(adaylar) > 1 else {"url": ""}
        if sub is main:
            sub = {"url": ""}
        kanallar.append(
            {
                "channel": no,
                "source_token": kaynak,
                "name": f"{taban} · Kanal {no}",
                "main_url": main["url"],
                "sub_url": sub.get("url") or "",
                "profile_token": main["token"],
            }
        )
    return kanallar


def _rtsp_portlari(rtsp_port: int) -> list[int]:
    portlar = [int(rtsp_port or 554)]
    for p in (554, 8554, 10554):
        if p not in portlar:
            portlar.append(p)
    return portlar


def cihaz_baglan(
    ip: str,
    kullanici: str,
    sifre: str,
    xaddrs: str = "",
    cihaz_adi: str = "",
    onvif_port: int = 80,
    rtsp_port: int = 554,
    vendor: str = "auto",
    media_port: int = 0,
) -> dict:
    """
    DVR/NVR veya IP kameraya bağlanır; kanal listesi döner.

    ONVIF kapalıysa RTSP yol şablonlarıyla (Digest kimlikli) kanallar aranır.
    Üretici "auto" ise açık portlardan (XM 34567, Dahua 37777, Hikvision 8000)
    tahmin edilir.

    Returns:
        {ok, hata, hata_kod, kanallar, xaddrs, cihaz_adi, rtsp_port, vendor, gunluk, mac_address}
    """
    ip = (ip or "").strip()
    gunluk: list[str] = []
    bos = {
        "ok": False,
        "hata": "IP adresi gerekli.",
        "hata_kod": "ip",
        "kanallar": [],
        "xaddrs": xaddrs,
        "cihaz_adi": cihaz_adi,
        "rtsp_port": int(rtsp_port or 554),
        "vendor": vendor,
        "gunluk": gunluk,
        "mac_address": "",
    }
    if not ip:
        return bos
    if not (kullanici or "").strip():
        bos["hata"] = "Cihaz kullanıcı adı gerekli."
        bos["hata_kod"] = "auth"
        return bos

    vendor = (vendor or "auto").lower()
    if vendor == "auto":
        tahmin, acik_portlar = uretici_tahmin(ip, int(media_port or 0))
        if acik_portlar:
            gunluk.append(f"Açık üretici portları: {', '.join(str(p) for p in acik_portlar)}")
        if tahmin:
            vendor = tahmin
            gunluk.append(f"Üretici tahmini: {tahmin}")
    bos["vendor"] = vendor

    cihaz, cap, hata = _endpoint_bul(
        ip, kullanici, sifre, xaddrs, int(onvif_port or 80), vendor
    )
    onvif_auth = hata == "auth"
    if cihaz and not onvif_auth:
        gunluk.append(f"ONVIF servisi bulundu: {cihaz}")
    elif onvif_auth:
        gunluk.append("ONVIF açık ama kullanıcı/şifre reddedildi.")
    else:
        gunluk.append(f"ONVIF yanıtı yok ({_hata_yaz(hata)})")

    kanallar: list[dict] = []
    if not onvif_auth:
        adresler = _xaddrs(cap) if cap else []
        media = _media_url_sec(adresler, cihaz) if cihaz else ""
        if not media and cap:
            media = _servis_adres(cap, "media")
        if not media and cihaz:
            ayr = urlparse(cihaz)
            media = f"{ayr.scheme}://{ayr.netloc}/onvif/media_service"

        if media:
            profiller, media2 = _profilleri_cek(media, kullanici, sifre)
            if not profiller:
                kaynak_xml = _posta(
                    media,
                    f'<trt:GetVideoSources xmlns:trt="{_NS_TRT}"/>',
                    kullanici,
                    sifre,
                    soap_action=f"{_NS_TRT}/GetVideoSources",
                    zaman_asimi=6,
                )
                for token in _kaynaklari_ayikla(kaynak_xml):
                    profiller.append(
                        {"token": token, "name": token, "source_token": token, "width": 0}
                    )
            if profiller:
                gunluk.append(f"ONVIF profil sayısı: {len(profiller)}")
            uri_map: dict[str, str] = {}
            with ThreadPoolExecutor(max_workers=4) as havuz:
                isler = {
                    havuz.submit(_stream_uri, media, p["token"], kullanici, sifre, media2): p["token"]
                    for p in profiller
                }
                for gelecek in as_completed(isler):
                    token = isler[gelecek]
                    try:
                        uri_map[token] = gelecek.result() or ""
                    except Exception:
                        uri_map[token] = ""
            kanallar = _kanallara_grupla(profiller, uri_map, kullanici, sifre, cihaz_adi, ip)
            if kanallar:
                gunluk.append(f"ONVIF ile {len(kanallar)} kanal alındı.")

    kullanilan_port = int(rtsp_port or 554)
    rtsp_durum = ""
    if not kanallar:
        for port in _rtsp_portlari(rtsp_port):
            if not port_acik(ip, port):
                gunluk.append(f"RTSP portu {port} kapalı.")
                rtsp_durum = rtsp_durum or "kapali"
                continue
            gunluk.append(f"RTSP portu {port} açık, yol şablonları deneniyor…")
            bulunan, durum = kanallari_bul(
                ip, port, kullanici, sifre, vendor, cihaz_adi or ip
            )
            rtsp_durum = durum
            if bulunan:
                kanallar = bulunan
                kullanilan_port = port
                gunluk.append(f"RTSP ile {len(bulunan)} kanal bulundu (port {port}).")
                break
            if durum == "auth":
                gunluk.append("RTSP kullanıcı/şifre reddedildi.")
                break
            gunluk.append("Bilinen RTSP yollarının hiçbiri yanıt vermedi.")

    if not kanallar:
        if onvif_auth or rtsp_durum == "auth":
            mesaj = (
                "Kullanıcı adı veya şifre cihaz tarafından reddedildi. "
                "DVR menüsündeki kullanıcıyı kullanın; bazı cihazlarda ONVIF için ayrı kullanıcı açmanız gerekir."
            )
        elif rtsp_durum == "kapali":
            mesaj = (
                f"{ip} adresine RTSP (554) ve ONVIF portlarından ulaşılamadı. "
                "IP doğru mu, cihaz aynı ağda mı ve RTSP açık mı kontrol edin."
            )
        elif rtsp_durum == "yol_yok":
            mesaj = (
                "Cihaza bağlanıldı ama bilinen RTSP yolları eşleşmedi. "
                "Üreticiyi seçip yeniden deneyin veya kanalları elle oluşturun."
            )
        else:
            mesaj = (
                "Cihaza ulaşıldı ama kamera listesi alınamadı. "
                "ONVIF'i cihaz menüsünden açın veya kanalları elle oluşturun."
            )
        if onvif_auth or rtsp_durum == "auth":
            kod = "auth"
        elif rtsp_durum == "kapali":
            kod = hata if hata in ("timeout", "refused", "baglanti") else "kapali"
        elif rtsp_durum == "yol_yok":
            kod = "yol_yok"
        else:
            kod = hata or "yanit_yok"
        return {
            "ok": False,
            "hata": mesaj,
            "hata_kod": kod,
            "kanallar": [],
            "xaddrs": cihaz or xaddrs,
            "cihaz_adi": cihaz_adi,
            "rtsp_port": kullanilan_port,
            "vendor": vendor,
            "gunluk": gunluk,
            "mac_address": mac_coz_ip(ip),
        }

    mac = _mac_topla(ip, cihaz, kullanici, sifre)
    if mac:
        gunluk.append(f"MAC: {mac}")
    return {
        "ok": True,
        "hata": "",
        "hata_kod": "",
        "kanallar": kanallar,
        "xaddrs": cihaz or xaddrs,
        "cihaz_adi": cihaz_adi or ip,
        "rtsp_port": kullanilan_port,
        "vendor": vendor,
        "gunluk": gunluk,
        "mac_address": mac,
    }


def _ag_on_eki(ip: str) -> str:
    parca = (ip or "").split(".")
    if len(parca) != 4:
        return ""
    return ".".join(parca[:3])


def _ping_var(host: str, milisaniye: int = 900) -> bool:
    """ICMP ile cihazın ağda yanıt verip vermediğine bakar."""
    try:
        if os.name == "nt":
            komut = ["ping", "-n", "1", "-w", str(milisaniye), host]
        else:
            komut = ["ping", "-c", "1", "-W", "1", host]
        tamam = subprocess.run(
            komut,
            capture_output=True,
            timeout=3,
            check=False,
        )
        return tamam.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def cihaz_tani(
    ip: str,
    kullanici: str,
    sifre: str,
    onvif_port: int = 80,
    rtsp_port: int = 554,
    media_port: int = 0,
) -> list[str]:
    """Bağlanamama nedenini bulmak için port ve protokol raporu üretir."""
    ip = (ip or "").strip()
    satirlar: list[str] = []
    if not ip:
        return ["IP adresi girilmedi."]

    yerel = yerel_ipv4_adresleri()
    satirlar.append(f"Hedef cihaz: {ip}")
    if yerel:
        satirlar.append(f"Bu bilgisayar: {', '.join(yerel)}")
    else:
        satirlar.append("Bu bilgisayar: IPv4 adresi bulunamadı (kablosuz/ethernet kapalı olabilir).")

    hedef_on = _ag_on_eki(ip)
    ayni = [a for a in yerel if _ag_on_eki(a) == hedef_on]
    if yerel and not ayni:
        satirlar.append(
            f"Ağ eşleşmiyor: cihaz {hedef_on}.x, bilgisayar "
            f"{', '.join(_ag_on_eki(a) + '.x' for a in yerel)}."
        )
        satirlar.append(
            "KobiCAM yalnızca kendi ağındaki cihazlara bağlanır. "
            "Bilgisayarı DVR ile aynı modem/switch'e bağlayın."
        )
    elif ayni:
        satirlar.append(f"Aynı alt ağ: {hedef_on}.x")

    ping = _ping_var(ip)
    satirlar.append(f"Ping (ICMP): {'yanıt var' if ping else 'yanıt yok'}")
    satirlar.append("")

    port_listesi = [
        (int(rtsp_port or 554), "RTSP"),
        (int(onvif_port or 80), "ONVIF/HTTP"),
        (int(media_port or 34567), "Media port (XM)"),
        (8000, "Hikvision SDK / ONVIF"),
        (8899, "XM ONVIF"),
        (37777, "Dahua SDK"),
        (34567, "XM SDK"),
    ]
    gorulen: set[int] = set()
    acik: list[int] = []
    for port, etiket in port_listesi:
        if port in gorulen:
            continue
        gorulen.add(port)
        if port_acik(ip, port, 0.8):
            acik.append(port)
            satirlar.append(f"Port {port} ({etiket}): açık")
        else:
            satirlar.append(f"Port {port} ({etiket}): kapalı")

    if not acik:
        satirlar.append("")
        if not ping:
            satirlar.append(
                "Sonuç: bu IP bu ağda yok. Şifre ve port henüz denenmedi; "
                "paket cihaza hiç ulaşmıyor. Tarayıcıda http://%s da açılmaz."
                % ip
            )
            satirlar.append("")
            satirlar.append("Sık nedenler:")
            satirlar.append(
                "• PC ve DVR aynı switch/modemde değil. Kamera switch'i ayrıysa "
                "o switch'ten PC'nin bağlı olduğu modeme bir kablo gerekir."
            )
            satirlar.append(
                "• DVR'da DHCP açık olduğu için IP değişmiş olabilir. "
                "Cihazın Ağ Ayarı ekranındaki IP'yi şimdi okuyup yukarıdaki "
                "'Bu bilgisayar' adresiyle karşılaştırın (ikisi de 192.168.1.x gibi aynı üç sayıyla başlamalı)."
            )
            satirlar.append(
                "• Modemde 'AP Isolation / kablosuz izolasyon / misafir ağ' açıksa "
                "Wi-Fi'deki PC kablolu DVR'ı göremez (kablolu PC'de bu genelde olmaz)."
            )
            satirlar.append(
                "• Windows güvenlik duvarı giden bağlantıyı genelde engellemez. "
                "Tarayıcıda arayüz yoksa sorun KobiCAM değildir."
            )
        else:
            satirlar.append(
                "Cihaz ping'e yanıt veriyor ama kamera portları kapalı. "
                "Tarayıcıda http://%s açılmıyorsa DVR web/ONVIF/RTSP servisleri kapalıdır; "
                "cihaz menüsünden HTTP, RTSP ve ONVIF'i açın."
                % ip
            )
        return satirlar

    tahmin, _acik = uretici_tahmin(ip, int(media_port or 0))
    if tahmin:
        satirlar.append("")
        satirlar.append(f"Üretici tahmini: {tahmin}")

    cihaz, _cap, hata = _endpoint_bul(
        ip, kullanici, sifre, "", int(onvif_port or 80), tahmin
    )
    satirlar.append("")
    if hata == "auth":
        satirlar.append("ONVIF: açık, kullanıcı/şifre reddedildi.")
    elif cihaz:
        satirlar.append(f"ONVIF: çalışıyor ({cihaz})")
    else:
        satirlar.append(f"ONVIF: yanıt yok ({_hata_yaz(hata)})")

    if kullanici:
        for port in _rtsp_portlari(rtsp_port):
            if not port_acik(ip, port):
                continue
            _sablon, durum = sablon_bul(ip, port, kullanici, sifre, tahmin or "auto")
            if durum == "ok":
                satirlar.append(f"RTSP {port}: yayın yolu bulundu.")
            elif durum == "auth":
                satirlar.append(f"RTSP {port}: kullanıcı/şifre reddedildi.")
            elif durum == "yol_yok":
                satirlar.append(f"RTSP {port}: bağlanıldı, bilinen yol eşleşmedi.")
            else:
                satirlar.append(f"RTSP {port}: yanıt yok.")
            break
    return satirlar


def medya_kanallari_kesfet(
    ip: str,
    kullanici: str,
    sifre: str,
    xaddrs: str = "",
    cihaz_adi: str = "",
) -> list[dict]:
    """Eski arayüz: yalnızca kanal listesi."""
    return cihaz_baglan(ip, kullanici, sifre, xaddrs, cihaz_adi).get("kanallar") or []
