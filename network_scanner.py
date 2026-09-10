"""
ONVIF WS-Discovery (UDP 3702) ve RTSP (TCP 554) ağ tarayıcısı.

QObject olarak kalır; ana pencere QThread.moveToThread ile arka plana alır.
Yalnızca yerel arayüzlerin /24 ağları taranır (ör. 10.0.0.0/8'in tamamı değil).
"""

from __future__ import annotations

import ctypes
import os
import re
import socket
import struct
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


# WS-Discovery multicast hedefi
_WS_ADRES = "239.255.255.250"
_WS_PORT = 3702
_WS_DINLEME_SN = 3.0

_RTSP_PORT = 554
_RTSP_TIMEOUT = 0.35
_RTSP_WORKERS = 96

# Kamera / kayıt cihazına özgü portlar. 80 taranmaz: modem, yazıcı gibi
# cihazlar listeyi kirletiyor.
_CIHAZ_PORTLARI = (
    (554, "rtsp"),
    (8000, "hikvision"),
    (8899, "xm-onvif"),
    (34567, "xm"),
    (37777, "dahua"),
)

# Yalnızca RFC1918 / link-local ağlar taranır
_OZEL_AGLAR = (
    ("10.0.0.0", 8),
    ("172.16.0.0", 12),
    ("192.168.0.0", 16),
    ("169.254.0.0", 16),
)

# Tip filtresi olmayan Probe — ucuz kameralar Types'ı yok sayabilir
_PROBE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
  <e:Header>
    <w:MessageID>uuid:{mid}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe/>
  </e:Body>
</e:Envelope>
"""


def _ip_int(ip: str) -> int:
    parca = ip.split(".")
    return (
        (int(parca[0]) << 24)
        | (int(parca[1]) << 16)
        | (int(parca[2]) << 8)
        | int(parca[3])
    )


def _ozel_ag_mi(ip: str) -> bool:
    try:
        deger = _ip_int(ip)
    except (ValueError, IndexError):
        return False
    for ag, prefiks in _OZEL_AGLAR:
        maske = (0xFFFFFFFF << (32 - prefiks)) & 0xFFFFFFFF
        if (deger & maske) == (_ip_int(ag) & maske):
            return True
    return False


def yerel_ipv4_adresleri() -> list[str]:
    """Aktif IPv4 arayüzlerini (loopback hariç) toplamaya çalışır."""
    ipler: list[str] = []

    try:
        soket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        soket.connect(("8.8.8.8", 80))
        ipler.append(soket.getsockname()[0])
        soket.close()
    except OSError:
        pass

    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = bilgi[4][0]
            if not ip.startswith("127."):
                ipler.append(ip)
    except OSError:
        pass

    tekil: list[str] = []
    for ip in ipler:
        if ip not in tekil and not ip.startswith("127."):
            tekil.append(ip)
    return tekil


def _xaddrs_hostlari(xaddrs: str) -> list[str]:
    """ONVIF XAddrs metninden IPv4 host'ları çıkarır."""
    hostlar: list[str] = []
    for jeton in xaddrs.split():
        try:
            ayr = urlparse(jeton.strip())
        except ValueError:
            continue
        host = ayr.hostname
        if host and "." in host and ":" not in host:
            hostlar.append(host)
    return hostlar


def _kapsam_adi(metin: str) -> str:
    """wsd:Scopes içinden onvif name değerini okur."""
    eslesme = re.search(
        r"onvif://www\.onvif\.org/name/([^\s<]+)",
        metin,
        re.IGNORECASE,
    )
    if not eslesme:
        return ""
    return unquote(eslesme.group(1)).replace("_", " ").strip()


def _tcp_port_acik(ip: str, port: int, timeout: float) -> bool:
    soket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    soket.settimeout(timeout)
    try:
        return soket.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        soket.close()


def tcp_port_acik(ip: str, port: int, timeout: float = 0.25) -> bool:
    """Harici çağrılar için TCP yoklama."""
    return _tcp_port_acik(ip, port, timeout)


_MAC_RE = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){5}$")
_ARP_SATIR = re.compile(
    r"(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})",
    re.IGNORECASE,
)


def mac_normalize(deger: str | None) -> str:
    """MAC'i AA:BB:CC:DD:EE:FF yapar; geçersizse boş dize."""
    ham = re.sub(r"[^0-9A-Fa-f]", "", deger or "")
    if len(ham) != 12:
        return ""
    mac = ":".join(ham[i : i + 2] for i in range(0, 12, 2)).upper()
    return mac if _MAC_RE.match(mac) else ""


def arp_ciktisindan_mac(metin: str, ip: str) -> str:
    """`arp -a` çıktısından verilen IPv4 için MAC okur."""
    ip = (ip or "").strip()
    if not ip:
        return ""
    for satir in (metin or "").splitlines():
        es = _ARP_SATIR.search(satir)
        if not es:
            continue
        if es.group(1) == ip:
            return mac_normalize(es.group(2))
    return ""


def _sendarp_mac(ip: str) -> str:
    if sys.platform != "win32":
        return ""
    try:
        iphlpapi = ctypes.windll.Iphlpapi
        dest = struct.unpack("I", socket.inet_aton(ip))[0]
        buf = ctypes.create_string_buffer(8)
        uzunluk = ctypes.c_ulong(6)
        kod = iphlpapi.SendARP(dest, 0, buf, ctypes.byref(uzunluk))
        if kod != 0 or uzunluk.value < 6:
            return ""
        return mac_normalize(":".join(f"{b:02X}" for b in buf.raw[:6]))
    except Exception:
        return ""


def _arp_komut_mac(ip: str) -> str:
    bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        komut = ["arp", "-a", ip] if os.name == "nt" else ["arp", "-n", ip]
        tamam = subprocess.run(
            komut,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            creationflags=bayrak,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return arp_ciktisindan_mac((tamam.stdout or "") + (tamam.stderr or ""), ip)


def mac_coz_ip(ip: str) -> str:
    """IPv4 için yerel ARP tablosundan MAC döndürür."""
    ip = (ip or "").strip()
    if not ip:
        return ""
    mac = _sendarp_mac(ip)
    if mac:
        return mac
    return _arp_komut_mac(ip)


def yerel_ag_hedefleri() -> list[str]:
    """Yerel RFC1918 /24 ağlarındaki taranacak IPv4 listesi."""
    hedefler: list[str] = []
    kendi = set(yerel_ipv4_adresleri())
    gorulen_ag: set[str] = set()
    for ip in sorted(kendi):
        if not _ozel_ag_mi(ip):
            continue
        parca = ip.split(".")
        ag_anahtari = ".".join(parca[:3])
        if ag_anahtari in gorulen_ag:
            continue
        gorulen_ag.add(ag_anahtari)
        for son in range(1, 255):
            aday = f"{ag_anahtari}.{son}"
            if aday not in kendi:
                hedefler.append(aday)
    return hedefler


class NetworkScanner(QObject):
    """Lokal ağdaki ONVIF / RTSP cihazlarını tarar."""

    camera_found = pyqtSignal(str, int, str, dict)
    scan_finished = pyqtSignal()
    scan_error = pyqtSignal(str)
    scan_progress = pyqtSignal(int, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._iptal = False
        self._calisiyor = False
        self._bulunan: set[str] = set()

    def cancel(self) -> None:
        """Devam eden taramayı durdurmak için bayrak (GUI thread'den çağrılabilir)."""
        self._iptal = True

    @pyqtSlot()
    def start_scan(self) -> None:
        """ONVIF ardından RTSP 554 taramasını çalıştırır."""
        if self._calisiyor:
            return
        self._calisiyor = True
        self._iptal = False
        self._bulunan = set()
        try:
            self.scan_progress.emit(0, 0)
            self._onvif_tara()
            if not self._iptal:
                self._rtsp_tara()
        except Exception as hata:  # noqa: BLE001 — tarayıcı UI'ya hata iletsin
            self.scan_error.emit(str(hata))
        finally:
            self._calisiyor = False
            self.scan_finished.emit()

    def _kaydet(self, ip: str, port: int, kaynak: str, bilgi: dict) -> None:
        if ip in self._bulunan:
            return
        self._bulunan.add(ip)
        paket = dict(bilgi or {})
        if not mac_normalize(str(paket.get("mac_address") or "")):
            paket["mac_address"] = mac_coz_ip(ip)
        self.camera_found.emit(ip, port, kaynak, paket)

    def _onvif_tara(self) -> None:
        """UDP 3702 WS-Discovery Probe gönderir ve yanıtları dinler."""
        probe = _PROBE_XML.format(mid=str(uuid.uuid4())).encode("utf-8")
        arayuzler = yerel_ipv4_adresleri()
        if not arayuzler:
            return

        soket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            soket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            soket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
            soket.settimeout(0.25)
            soket.bind(("", 0))

            for arayuz in arayuzler:
                if self._iptal:
                    return
                try:
                    soket.setsockopt(
                        socket.IPPROTO_IP,
                        socket.IP_MULTICAST_IF,
                        socket.inet_aton(arayuz),
                    )
                    soket.sendto(probe, (_WS_ADRES, _WS_PORT))
                except OSError:
                    continue

            bitis = time.monotonic() + _WS_DINLEME_SN
            while time.monotonic() < bitis and not self._iptal:
                try:
                    veri, adres = soket.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    break
                self._onvif_yanit_isle(veri, adres[0])
        finally:
            soket.close()

    def _onvif_yanit_isle(self, veri: bytes, kaynak_ip: str) -> None:
        try:
            metin = veri.decode("utf-8", errors="replace")
        except Exception:
            return
        if "ProbeMatch" not in metin and "XAddrs" not in metin:
            return

        xaddrs_es = re.search(r"XAddrs[^>]*>([^<]+)", metin, re.IGNORECASE)
        xaddrs = xaddrs_es.group(1).strip() if xaddrs_es else ""
        hostlar = _xaddrs_hostlari(xaddrs) or ([kaynak_ip] if kaynak_ip else [])
        ad = _kapsam_adi(metin)

        for host in hostlar:
            bilgi = {
                "name": ad or f"ONVIF {host}",
                "xaddrs": xaddrs,
            }
            self._kaydet(host, _RTSP_PORT, "onvif", bilgi)

    def _rtsp_hedefler(self) -> list[str]:
        """Yerel /24 ağlardaki taranacak IPv4 listesini üretir."""
        return yerel_ag_hedefleri()

    def _rtsp_tara(self) -> None:
        """Kamera / DVR portlarını sınırlı eşzamanlılıkla tarar."""
        hedefler = self._rtsp_hedefler()
        if not hedefler:
            self.scan_progress.emit(0, 0)
            return

        isler_listesi = [(ip, port, tur) for ip in hedefler for port, tur in _CIHAZ_PORTLARI]
        toplam = len(isler_listesi)
        tamamlanan = 0
        acik_portlar: dict[str, list[tuple[int, str]]] = {}

        with ThreadPoolExecutor(max_workers=_RTSP_WORKERS) as havuz:
            isler = {
                havuz.submit(_tcp_port_acik, ip, port, _RTSP_TIMEOUT): (ip, port, tur)
                for ip, port, tur in isler_listesi
            }
            for gelecek in as_completed(isler):
                if self._iptal:
                    for kalan in isler:
                        kalan.cancel()
                    break
                ip, port, tur = isler[gelecek]
                tamamlanan += 1
                if tamamlanan % 32 == 0 or tamamlanan == toplam:
                    self.scan_progress.emit(tamamlanan, toplam)
                try:
                    acik = gelecek.result()
                except Exception:
                    acik = False
                if acik:
                    acik_portlar.setdefault(ip, []).append((port, tur))

        for ip, portlar in sorted(acik_portlar.items()):
            portlar.sort()
            rtsp = next((p for p, _t in portlar if p == _RTSP_PORT), _RTSP_PORT)
            turler = ",".join(t for _p, t in portlar)
            kayit_cihazi = any(p in (8000, 8899, 34567, 37777) for p, _t in portlar)
            etiket = "Kayıt cihazı" if kayit_cihazi else "RTSP cihazı"
            self._kaydet(
                ip,
                rtsp,
                turler,
                {"name": f"{etiket} {ip}", "ports": [p for p, _t in portlar]},
            )

        if not self._iptal:
            self.scan_progress.emit(toplam, toplam)
